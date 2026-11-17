"""Alt ajan tanımındaki ayarların koşuya uygulanması (P-034).

`.claude/agents/<ad>.md` frontmatter'ındaki `model`, `permissionMode`, `maxTurns`, `skills`,
`mcpServers`, `effort`, `disallowedTools` alanları burada Fusion karşılıklarına çevrilir.
İzin kipi güncel üst-çocuk matrisini izler; bypass yalnız üstten devralınır. Araç
kümesi yalnız daralır, model/efor yalnız bu alt ajanın çağrılarını değiştirir.
`background`, `isolation` ve `hooks` okunur ve katalogda gösterilir; Fusion'da alt ajan tur
içinde biter, bu yüzden uygulanmaz. Çalışma ağacı izolasyonu tanımdan değil çağrıdan gelir:
`subtask(izolasyon="worktree")` (bkz. docs/YETENEKLER.md).
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ...config.agent_launch_settings import AgentLaunchConfig
from ...config.trust import is_file_trusted
from ...core.errors import ConfigError
from ...core.reasoning import ReasoningEffort
from ...core.types import ModelSpec
from ...memory.plain_memory import PlainMemory, open_agent_memory
from ...tools.capabilities import Capability, load_skill_text
from ...tools.plugin_capabilities import PLUGIN_SOURCE
from .agent_launch_model import CLAUDE_ALIASES, resolve_agent_model
from .approval import (
    ApprovalMode,
    ApprovalPolicy,
    ApprovalRequest,
    Decision,
    Denial,
    parse_mode,
)
from .approval import strictest_mode as strictest_mode

if TYPE_CHECKING:
    from ...config.models import Config
    from .loop import AgentDeps
    from .team import Persona

_LOG = logging.getLogger(__name__)

#: Başlangıçta yüklenecek beceri sayısı ve toplam metin bütçesi (Claude Code: ≤32 beceri).
SKILL_PRELOAD_LIMIT = 32
SKILL_PRELOAD_CHARS = 24_000
#: Beceri çözümleyicisinin eski miras sözleşmesi; alt ajan ailesi ayrıca çözülür.
INHERIT_MODELS = frozenset({"inherit", "sonnet", "opus", "haiku", "fable"})
CLAUDE_MODEL_ALIASES = CLAUDE_ALIASES


def _child_mode(
    parent: ApprovalMode, requested: ApprovalMode, *, auto_available: bool = True
) -> ApprovalMode:
    """Güncel Claude matrisi: varsayılan üst seçebilir; bypass'a yükseltemez."""
    if requested is ApprovalMode.AUTO and not auto_available:
        return parent
    if (
        parent in (ApprovalMode.SECURITY, ApprovalMode.DONT_ASK)
        and requested is not ApprovalMode.BYPASS
    ):
        return requested
    return parent


class LabeledPolicy:
    """Alt ajanın her onay isteğine kimliğini basan sarmalayıcı: kart "kim istiyor" der."""

    def __init__(self, inner: ApprovalPolicy, label: str) -> None:
        self._inner = inner
        self._label = label

    async def decide(self, request: ApprovalRequest) -> Decision | Denial:
        if request.agent_label:
            return await self._inner.decide(request)
        return await self._inner.decide(dataclasses.replace(request, agent_label=self._label))


def agent_label(persona: Persona, sub_id: str) -> str:
    return f"{persona.title} ({sub_id})"


def agent_permission_mode(agent: Capability) -> str:
    """Eklenti izin alanını kaynak bilgisi kişiliğe aktarılmadan önce yok say."""
    return "" if agent.source == PLUGIN_SOURCE else agent.permission_mode


def requested_mode(persona: Persona) -> ApprovalMode | None:
    """`permissionMode` alanını kipe çevir; tanınmayan değer yok sayılır (uyarıyla)."""
    if not persona.permission_mode:
        return None
    try:
        return parse_mode(persona.permission_mode)
    except ValueError:
        _LOG.warning(
            "alt ajan izin kipi tanınmadı",
            extra={"ajan": persona.name, "kip": persona.permission_mode},
        )
        return None


def child_policies(
    deps: AgentDeps, persona: Persona, label: str
) -> tuple[ApprovalPolicy, Callable[[], ApprovalPolicy] | None]:
    """Alt ajanın politikası ve tur içi yeniden kurucusu aynı kip matrisini izler."""
    wanted = requested_mode(persona)
    current = getattr(deps, "approval_mode", None)
    builder = getattr(deps, "policy_for_mode", None)
    if wanted is None or current is None or builder is None:
        factory = deps.policy_factory
        return (
            LabeledPolicy(deps.policy, label),
            (lambda: LabeledPolicy(factory(), label)) if factory is not None else None,
        )

    def _build() -> ApprovalPolicy:
        return LabeledPolicy(
            builder(_child_mode(current(), wanted, auto_available=can_use_auto(deps))), label
        )

    return _build(), _build


def child_approval_mode(deps: AgentDeps, persona: Persona) -> Callable[[], ApprovalMode] | None:
    """Torun, oturum yerine kendi üstünün güncel matrisle seçilen kipini görür."""
    current = getattr(deps, "approval_mode", None)
    wanted = requested_mode(persona)
    if current is None or wanted is None:
        return current
    return lambda: _child_mode(current(), wanted, auto_available=can_use_auto(deps))


def child_model(
    persona: Persona,
    parent: ModelSpec,
    *,
    candidates: tuple[ModelSpec, ...] = (),
    launch: AgentLaunchConfig | None = None,
    invocation_model: str = "",
) -> ModelSpec | None:
    """Mevcut resolver yolunda yapılandırılmış model önceliğini uygula."""
    validate_agent_hooks(persona)
    selected = resolve_agent_model(
        persona.model,
        parent,
        candidates=candidates,
        launch=launch or AgentLaunchConfig(),
        invocation_model=invocation_model,
        keep_builtin_model=persona.source == "fusion" and persona.name == "explore",
    )
    if selected is None or selected is parent:
        return selected
    return dataclasses.replace(selected, name=f"ajan:{persona.name}")


def can_use_auto(deps: AgentDeps) -> bool:
    """Kapalı veya seçilen modelde desteklenmeyen otomatik kipi açma."""
    settings = deps.config.agent_launch
    selected = deps.active_model_override or deps.config.agent
    return not settings.disable_auto_mode and (
        not settings.auto_supported_models or selected.model in settings.auto_supported_models
    )


def main_approval_mode(config: Config, persona: Persona, parent: ApprovalMode) -> ApprovalMode:
    """Kişilik seçilirken istenen kipi bir kez çöz; sonraki kullanıcı seçimi üstündür."""
    wanted = requested_mode(persona)
    if wanted is None:
        return parent
    settings = config.agent_launch
    available = not settings.disable_auto_mode and (
        not settings.auto_supported_models or config.agent.model in settings.auto_supported_models
    )
    return _child_mode(parent, wanted, auto_available=available)


def child_config(config: Config, persona: Persona) -> Config:
    """`effort` alanı geçerliyse yalnız bu alt ajanın düşünme yoğunluğunu değiştirir."""
    if not persona.effort:
        return config
    try:
        effort = ReasoningEffort(persona.effort.lower())
    except ValueError:
        _LOG.warning(
            "alt ajan eforu tanınmadı", extra={"ajan": persona.name, "efor": persona.effort}
        )
        return config
    return dataclasses.replace(
        config, runtime=dataclasses.replace(config.runtime, reasoning_effort=effort)
    )


def main_agent_config(
    config: Config, persona: Persona, *, root: Path | None = None, home: Path | None = None
) -> Config:
    """Ana ajan modeli/eforu ve izinli inline MCP; alt ajan ortam FORCE'u uygulanmaz."""
    validate_agent_hooks(persona)
    updated = child_config(config, persona)
    selected = child_model(
        persona,
        config.agent,
        candidates=config.candidates,
        launch=dataclasses.replace(
            config.agent_launch, subagent_model="", force_subagent_model=False
        ),
    )
    if selected is not None:
        updated = dataclasses.replace(updated, agent=selected)
    return agent_mcp_config(updated, persona, root=root, home=home)


def validate_agent_hooks(persona: Persona) -> None:
    """Uygulanamayan koruyucu kancayı düşürüp ajanı denetimsiz çalıştırma."""
    if persona.hook_definitions.skipped:
        raise ConfigError(
            "Ajanın kanca tanımı desteklenmiyor; ajan çalıştırılmadı. "
            "Desteklenen command/http alanlarını kullanın; "
            "args, async ve diğer desteklenmeyen kanca seçeneklerini düzeltin."
        )


def agent_mcp_config(
    config: Config, persona: Persona, *, root: Path | None = None, home: Path | None = None
) -> Config:
    """Kaynak güveni doğrulanan inline MCP tanımlarını mevcut yapılandırmaya ekle."""
    updated = config
    servers = persona.inline_mcp_servers
    if servers and (
        root is None or not is_trusted_agent_definition(config, persona, root=root, home=home)
    ):
        _LOG.warning(
            "Ajanın inline MCP tanımının kaynağı doğrulanamadı; "
            "tanımı kendi kapsamındaki güven yoluyla onaylayın."
        )
        servers = ()
    if servers:
        names = {server.name for server in servers}
        updated = dataclasses.replace(
            updated,
            mcp_servers=(
                *tuple(server for server in updated.mcp_servers if server.name not in names),
                *servers,
            ),
        )
    return updated


#: Ajan belleği olan üyeye kısıtlı araç kümesinde de açılan araçlar (P-055).
MEMORY_TOOL_NAMES = frozenset({"remember", "memory_read"})


def child_memory(deps: AgentDeps, persona: Persona) -> PlainMemory | None:
    """`memory: user|project|local` alanı varsa alt ajanın KENDİ belleği; yoksa None.

    Alt ajan projenin otomatik belleğini (P-036) devralmaz: Claude Code'da da ajan belleği
    ajana özeldir ve ana oturumun MEMORY.md'si alt ajana gitmez.
    """
    if not persona.memory_scope:
        return None
    return open_agent_memory(
        deps.config, deps.tool_context.root, persona.name, persona.memory_scope
    )


def preloaded_skills(deps: AgentDeps, persona: Persona) -> str:
    """`skills` listesindeki becerilerin metni; bulunamayan ad atlanır, bütçe aşılmaz."""
    library = deps.capabilities
    if library is None or not persona.skills:
        return ""
    parts: list[str] = []
    used = 0
    for name in persona.skills[:SKILL_PRELOAD_LIMIT]:
        item: Capability | None = library.get_skill(name)
        if item is None:
            _LOG.warning(
                "ön yüklenecek beceri bulunamadı", extra={"ajan": persona.name, "beceri": name}
            )
            continue
        remaining = SKILL_PRELOAD_CHARS - used
        if remaining <= 0:
            break
        text = load_skill_text(item.path, budget=remaining)
        used += len(text)
        parts.append(f"# Ön yüklenen beceri: {name}\n{text}")
    return "\n\n".join(parts)


def is_trusted_agent_definition(
    config: Config, persona: Persona, *, root: Path, home: Path | None = None
) -> bool:
    """Kaynak etiketi tek başına yetki vermez; gerçek kök/kimlik ve içerik doğrulanır."""
    path = persona.definition_path
    sources = frozenset(persona.source.split("+"))
    known = {"cli", "proje", "ek-kok", "managed", "fusion", "claude", "codex"}
    if path is None or not sources or not sources <= known:
        return False
    if (
        sources & {"proje", "ek-kok"}
        and home is not None
        and _inside_definition(path, root)
        and is_file_trusted(root, path)
    ):
        return True
    if "cli" in sources:
        identity = hashlib.sha256(persona.name.encode()).hexdigest()
        if path == root / ".cli-agents" / f"{identity}.md" and not path.exists():
            return True
    if "managed" in sources and any(
        _inside_definition(path, Path(folder) if Path(folder).is_absolute() else root / folder)
        for folder in config.agent_launch.managed_agent_roots
    ):
        return True
    if "fusion" in sources and _inside_definition(
        path, Path(__file__).parents[2] / "config" / "roster"
    ):
        return True
    if home is None:
        return False
    folders = {"claude": Path(".claude/agents"), "codex": Path(".codex/agents")}
    return any(
        source in sources and _inside_definition(path, home / relative)
        for source, relative in folders.items()
    )


def _inside_definition(path: Path, base: Path) -> bool:
    """Kaynak kökü veya alt bileşeni sembolik bağ olan tanıma yürütme izni verme."""
    try:
        relative = path.relative_to(base)
        path.resolve().relative_to(base.resolve())
    except (ValueError, OSError, RuntimeError):
        return False
    if (
        base.is_symlink()
        or base.parent.is_symlink()
        or not path.is_file()
        or path.suffix not in {".md", ".toml"}
    ):
        return False
    return not any(
        (base / Path(*relative.parts[:index])).is_symlink()
        for index in range(1, len(relative.parts) + 1)
    )

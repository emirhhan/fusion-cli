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
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...core.errors import ConfigError
from ...core.reasoning import ReasoningEffort
from ...core.types import ModelSpec
from ...memory.plain_memory import PlainMemory, open_agent_memory
from ...tools.capabilities import Capability, load_skill_text
from ...tools.plugin_capabilities import PLUGIN_SOURCE
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
CLAUDE_MODEL_ALIASES = INHERIT_MODELS - {"inherit"}
UNRESOLVED_MODEL_ALIAS = (
    "Alt ajan modeli '{model}' çözülemedi. candidates içinde bu takma adla veya "
    "Claude ailesiyle bir model yapılandırın ya da tam sağlayıcı/model kimliğini yazın."
)


def _child_mode(parent: ApprovalMode, requested: ApprovalMode) -> ApprovalMode:
    """Güncel Claude matrisi: varsayılan üst seçebilir; bypass'a yükseltemez."""
    if parent is ApprovalMode.SECURITY and requested is not ApprovalMode.BYPASS:
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
        return LabeledPolicy(builder(_child_mode(current(), wanted)), label)

    return _build(), _build


def child_approval_mode(deps: AgentDeps, persona: Persona) -> Callable[[], ApprovalMode] | None:
    """Torun, oturum yerine kendi üstünün güncel matrisle seçilen kipini görür."""
    current = getattr(deps, "approval_mode", None)
    wanted = requested_mode(persona)
    if current is None or wanted is None:
        return current
    return lambda: _child_mode(current(), wanted)


def child_model(
    persona: Persona, parent: ModelSpec, *, candidates: tuple[ModelSpec, ...] = ()
) -> ModelSpec | None:
    """Modeli mevcut havuzdan çöz; aynı aile ve katı seçim tam üst kimliğini korur."""
    model = persona.model.strip()
    wanted = model.lower()
    if parent.strict or not model or wanted == "inherit":
        return parent
    if wanted in CLAUDE_MODEL_ALIASES:
        if _claude_family(parent.model) == wanted:
            return parent
        candidate = next((item for item in candidates if item.name.lower() == wanted), None)
        if candidate is None:
            candidate = next(
                (item for item in candidates if _claude_family(item.model) == wanted), None
            )
        if candidate is None:
            raise ConfigError(UNRESOLVED_MODEL_ALIAS.format(model=model))
        fallbacks = tuple(item for item in parent.models if item not in candidate.models)
        return dataclasses.replace(
            candidate, name=f"ajan:{persona.name}", fallback=(*candidate.fallback, *fallbacks)
        )
    if model.startswith("claude-"):
        model = f"anthropic/{model}"
    if "/" not in model:
        _LOG.warning("alt ajan modeli tanınmadı", extra={"ajan": persona.name, "model": model})
        return None
    if model == parent.model:
        return parent
    return ModelSpec(name=f"ajan:{persona.name}", model=model, fallback=parent.models)


def _claude_family(model: str) -> str | None:
    """Sağlayıcı yolunu ve bağlam sonekini sürümden bağımsız aileye indirger."""
    tokens = re.split(r"[-_./:\[\]]+", model.lower())
    if "claude" not in tokens and "anthropic" not in tokens:
        return model.lower() if model.lower() in CLAUDE_MODEL_ALIASES else None
    return next((token for token in tokens if token in CLAUDE_MODEL_ALIASES), None)


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

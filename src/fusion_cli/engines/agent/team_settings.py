"""Alt ajan tanımındaki ayarların koşuya uygulanması (P-034).

`.claude/agents/<ad>.md` frontmatter'ındaki `model`, `permissionMode`, `maxTurns`, `skills`,
`mcpServers`, `effort`, `disallowedTools` alanları burada Fusion karşılıklarına çevrilir.
İlke: alt ajan üst ajanın güven sınırını GENİŞLETEMEZ — izin kipi yalnız sıkılaşır, araç
kümesi yalnız daralır, model/efor yalnız bu alt ajanın çağrılarını değiştirir.
`background`, `isolation` ve `hooks` okunur ve katalogda gösterilir; Fusion'da alt ajan tur
içinde biter ve kendi worktree'si yoktur, bu yüzden uygulanmaz (bkz. docs/YETENEKLER.md).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...core.reasoning import ReasoningEffort
from ...core.types import ModelSpec
from ...tools.capabilities import Capability, load_skill_text
from .approval import ApprovalMode, ApprovalPolicy, ApprovalRequest, Decision, parse_mode
from .approval import strictest_mode as strictest_mode

if TYPE_CHECKING:
    from ...config.models import Config
    from .loop import AgentDeps
    from .team import Persona

_LOG = logging.getLogger(__name__)

#: Başlangıçta yüklenecek beceri sayısı ve toplam metin bütçesi (Claude Code: ≤32 beceri).
SKILL_PRELOAD_LIMIT = 32
SKILL_PRELOAD_CHARS = 24_000
#: Üst ajanı kullan demek olan model takma adları (`inherit` ve Claude'un kısa adları).
INHERIT_MODELS = frozenset({"inherit", "sonnet", "opus", "haiku", "fable"})


class LabeledPolicy:
    """Alt ajanın her onay isteğine kimliğini basan sarmalayıcı: kart "kim istiyor" der."""

    def __init__(self, inner: ApprovalPolicy, label: str) -> None:
        self._inner = inner
        self._label = label

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.agent_label:
            return await self._inner.decide(request)
        return await self._inner.decide(dataclasses.replace(request, agent_label=self._label))


def agent_label(persona: Persona, sub_id: str) -> str:
    return f"{persona.title} ({sub_id})"


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
    """Alt ajanın politikası ve tur-içi yeniden kurucu: üst kipi SIKILAŞTIRIR, gevşetmez."""
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
        return LabeledPolicy(builder(strictest_mode(current(), wanted)), label)

    return _build(), _build


def child_model(persona: Persona, parent: ModelSpec) -> ModelSpec | None:
    """`model` alanı `<sağlayıcı>/<model>` ise bu alt ajana özel spec; takma ad = miras."""
    model = persona.model.strip()
    if not model or model.lower() in INHERIT_MODELS:
        return None
    if "/" not in model:
        _LOG.warning("alt ajan modeli tanınmadı", extra={"ajan": persona.name, "model": model})
        return None
    return ModelSpec(name=f"ajan:{persona.name}", model=model, fallback=parent.models)


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

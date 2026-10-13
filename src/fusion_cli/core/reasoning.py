"""Reasoning effort — modelin "düşünme" yoğunluğu.

Effort, çalışma profilinden (mode) AYRIDIR (master prompt §7.1): profil model/
sağlayıcı havuzunu seçer, effort seçilen model DESTEKLİYORSA düşünme yoğunluğunu
ayarlar. Model desteklemiyorsa hatalı parametre gönderilmez; sessizce en yakına
eşlenir ya da hiç gönderilmez.

Sağlayıcıların (OpenAI uyumlu `reasoning_effort`) kabul ettiği değerler kısıtlıdır;
altı seviyelik kullanıcı seçimi bu üçe indirgenir ve indirgeme kullanıcıya gösterilir.
"""

from __future__ import annotations

from enum import Enum

from .model_capability import ModelCapability


class ReasoningEffort(Enum):
    """Kullanıcının seçebildiği reasoning yoğunluğu."""

    #: Modele bırak — `reasoning_effort` parametresi hiç gönderilmez.
    AUTO = "auto"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    #: `high`'ın üstü; sağlayıcı desteklemezse en yakın (`high`) uygulanır.
    XHIGH = "xhigh"
    #: En yüksek; sağlayıcı desteklemezse en yakın (`high`) uygulanır.
    MAX = "max"


#: Effort → sağlayıcının kabul ettiği `reasoning_effort` değeri. `AUTO` haritada
#: YOKTUR: parametre gönderilmez, karar modele bırakılır. `xhigh`/`max` desteklenen
#: en yüksek seviyeye (`high`) eşlenir — geçersiz değer göndermek yerine.
_PROVIDER_LEVELS: dict[ReasoningEffort, str] = {
    ReasoningEffort.LOW: "low",
    ReasoningEffort.MEDIUM: "medium",
    ReasoningEffort.HIGH: "high",
    ReasoningEffort.XHIGH: "high",
    ReasoningEffort.MAX: "high",
}


def provider_value(effort: ReasoningEffort) -> str | None:
    """Effort'u sağlayıcının kabul ettiği değere eşle; `AUTO` için `None`."""
    return _PROVIDER_LEVELS.get(effort)


def is_downgraded(effort: ReasoningEffort) -> bool:
    """Seçilen seviye, desteklenen en yakına indirildi mi? (`xhigh`/`max` → `high`)"""
    mapped = provider_value(effort)
    return mapped is not None and mapped != effort.value


@dataclass(frozen=True, slots=True)
class ReasoningResolution:
    """Requested and actually applicable reasoning parameters."""
    requested: str | None
    applied: str | None
    reason: str = ""


def resolve_reasoning(requested: str | None, capability: ModelCapability) -> ReasoningResolution:
    """Apply only effort levels verified for this model identity."""
    if requested is None or requested == ReasoningEffort.AUTO.value:
        return ReasoningResolution(requested, None)
    if not capability.reasoning_efforts_verified:
        return ReasoningResolution(requested, None, "Modelin düşünme yoğunluğu desteği doğrulanmadı.")
    supported = capability.supported_reasoning_efforts
    if requested in supported:
        return ReasoningResolution(requested, requested)
    if requested in (ReasoningEffort.XHIGH.value, ReasoningEffort.MAX.value) and "high" in supported:
        return ReasoningResolution(requested, "high", "Seçilen yoğunluk desteklenmiyor; high uygulanıyor.")
    return ReasoningResolution(requested, None, "Model seçilen düşünme yoğunluğunu desteklemiyor.")

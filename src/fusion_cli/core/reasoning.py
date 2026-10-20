"""Düşünme yoğunluğu niyeti ve adaptör sınırındaki doğrulanmış çözümleme.

Profil model havuzunu seçer; yoğunluk ayrı bir tercihtir. Exact destek yalnız
modelin kendi doğrulanmış listesinde varsa uygulanır. Bilinmeyen/desteksiz
parametre gönderilmez; indirgeme yalnız kanıtlı high değeriyle yapılır.
Legacy provider_value saf uyumluluk eşlemesidir; yetenek doğrulaması değildir.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    """İstenen ve gerçekten gönderilebilen yoğunluğu birbirinden ayırır."""

    requested: str | None
    applied: str | None
    reason: str = ""


def resolve_reasoning(requested: str | None, capability: ModelCapability) -> ReasoningResolution:
    """Yalnız doğrulanmış değer gönderilir; bilinmeyen yetenek tahmin edilmez."""
    if requested is None or requested == ReasoningEffort.AUTO.value:
        return ReasoningResolution(requested, None)
    if not capability.reasoning_efforts_verified:
        return ReasoningResolution(
            requested, None, "Modelin düşünme yoğunluğu desteği doğrulanmadı."
        )
    supported = capability.supported_reasoning_efforts
    if requested in supported:
        return ReasoningResolution(requested, requested)
    if (
        requested in (ReasoningEffort.XHIGH.value, ReasoningEffort.MAX.value)
        and "high" in supported
    ):
        return ReasoningResolution(
            requested, "high", "Seçilen yoğunluk desteklenmiyor; high uygulanıyor."
        )
    return ReasoningResolution(requested, None, "Model seçilen düşünme yoğunluğunu desteklemiyor.")

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

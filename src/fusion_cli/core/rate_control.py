"""Hız sınırı denetiminin tiplenmiş ayarları ve paylaşılan defteri.

`HealthRegistry` ile birlikte taşınır: ikisi de "bu süreçteki model çağrıları ne
kadar dayanıklı" sorusunun cevabıdır ve sağlayıcı kurulan her yere zaten giden tek
nesne odur. Ayrı bir parametre olarak eklemek on dört çağrı yerini değiştirirdi.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .protocols import RateLedger


@dataclass(frozen=True, slots=True)
class RateControl:
    """Önden hız ayarı + süreçler arası soğuma paylaşımı."""

    ledger: RateLedger
    #: Sağlayıcı kimliği (`nvidia_nim`) → model başına dakikalık istek sınırı.
    #: Burada OLMAYAN sağlayıcı önden yavaşlatılmaz; yalnız 429 paylaşılır.
    per_minute: Mapping[str, float] = field(default_factory=dict)
    #: Hak için en fazla bu kadar beklenir; daha uzunsa çağrı yedeğe bırakılır.
    pace_max_wait_s: float = 0.0
    #: 429 alan model/anahtar bütün süreçlerde bu kadar atlanır.
    cooldown_s: float = 0.0

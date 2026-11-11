"""Hız sınırı denetiminin tiplenmiş ayarları ve paylaşılan defteri.

`HealthRegistry` ile birlikte taşınır: ikisi de "bu süreçteki model çağrıları ne
kadar dayanıklı" sorusunun cevabıdır ve sağlayıcı kurulan her yere zaten giden tek
nesne odur. Ayrı bir parametre olarak eklemek on dört çağrı yerini değiştirirdi.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .protocols import RateLedger

if TYPE_CHECKING:
    from .types import CompletionRequest


def rate_wait_fits(request: CompletionRequest, wait_s: float) -> bool:
    """Check the opening and task deadlines against their own clocks."""
    opening_at = request.rate_retry_opening_at
    if opening_at is not None and wait_s >= opening_at - asyncio.get_running_loop().time():
        return False
    deadline = request.rate_retry_deadline
    return deadline is None or wait_s < deadline.remaining_s()


@dataclass(frozen=True, slots=True)
class RateControl:
    """Önden hız ayarı + süreçler arası soğuma paylaşımı."""

    ledger: RateLedger
    #: Sağlayıcı kimliği → dakikalık sınır. Tam model kimliği, tek haklı kovayı seçer.
    #: Burada OLMAYAN sağlayıcı önden yavaşlatılmaz; yalnız 429 paylaşılır.
    per_minute: Mapping[str, float] = field(default_factory=dict)
    #: Hak için en fazla bu kadar beklenir; daha uzunsa çağrı yedeğe bırakılır.
    pace_max_wait_s: float = 0.0
    #: 429 alan model/anahtar bütün süreçlerde bu kadar atlanır.
    cooldown_s: float = 0.0

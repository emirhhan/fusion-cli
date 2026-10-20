"""Dış isteğin süresinden sunucu saatinde tek kez oluşturulan tur sınırı."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .protocols import Clock


@dataclass(frozen=True, slots=True)
class TurnDeadline:
    """Yerel saat ve bitiş; başka sürecin monoton timestamp'i taşınmaz."""

    clock: Clock
    expires_at: float

    @classmethod
    def from_duration(cls, value: object, clock: Clock) -> TurnDeadline | None:
        """Opsiyonel pozitif sonlu saniyeyi sınırla; boş giriş eski davranıştır."""
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Tur süresi pozitif ve sonlu saniye olmalı.")
        try:
            duration = float(value)
        except OverflowError as error:
            raise ValueError("Tur süresi sonlu saniye olmalı.") from error
        expires_at = clock.monotonic() + duration
        if duration <= 0 or not math.isfinite(duration) or not math.isfinite(expires_at):
            raise ValueError("Tur süresi pozitif ve sonlu saniye olmalı.")
        return cls(clock, expires_at)

    def remaining_s(self) -> float:
        """Aynı kök isteğin kalan süresi; devam turları bitişi tazelemez."""
        return self.expires_at - self.clock.monotonic()

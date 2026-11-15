"""Hesap başına artan bekleme: hatalı parola/kod denemelerini yavaşlatır, KİLİTLEMEZ.

Ölçüldü (30 Ekim): giriş, silme ve kurtarma uçları hatalı denemeyi sınırsız kabul ediyordu;
her deneme ≈90 ms scrypt, yani saniyede ~10 tahmin. Burada ilk `free_attempts` ardışık
hata bedavadır; sonrasında her hata beklemeyi ikiye katlar (tavan `max_delay_s`). Bekleme
sırasında gelen istekler sayacı BÜYÜTMEZ (saldırgan bekleme süresini uzatamaz, sahibi de
kendini kilitleyemez) ve sayaç `idle_reset_s` sessizlikten sonra sıfırlanır. Kalıcı kilit
yoktur: süre dolunca doğru parola her zaman girer. Durum bellektedir (süreç başına).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from ..core.protocols import Clock

__all__ = ["AttemptThrottle"]


@dataclass(frozen=True, slots=True)
class _Record:
    failures: int
    last_failure: float


class AttemptThrottle:
    """Anahtar (hesap) başına ardışık hata sayar; artan bekleme önerir."""

    def __init__(
        self,
        clock: Clock,
        *,
        free_attempts: int = 3,
        base_delay_s: float = 2.0,
        max_delay_s: float = 300.0,
        idle_reset_s: float = 900.0,
        max_keys: int = 1024,
    ) -> None:
        self._clock = clock
        self._free = max(1, free_attempts)
        self._base = base_delay_s
        self._max = max_delay_s
        self._idle_reset = idle_reset_s
        self._max_keys = max_keys
        self._records: OrderedDict[str, _Record] = OrderedDict()

    def _delay(self, failures: int) -> float:
        if failures < self._free:
            return 0.0
        return float(min(self._max, self._base * 2 ** (failures - self._free)))

    def retry_after(self, key: str) -> float:
        """Bu anahtar için yeni denemeye kalan saniye; 0 = şimdi denenebilir."""
        record = self._records.get(key)
        if record is None:
            return 0.0
        elapsed = self._clock.monotonic() - record.last_failure
        if elapsed >= self._idle_reset:
            del self._records[key]
            return 0.0
        return max(0.0, self._delay(record.failures) - elapsed)

    def record_failure(self, key: str) -> None:
        now = self._clock.monotonic()
        record = self._records.pop(key, None)
        failures = (
            1
            if record is None or now - record.last_failure >= self._idle_reset
            else (record.failures + 1)
        )
        self._records[key] = _Record(failures, now)
        while len(self._records) > self._max_keys:
            self._records.popitem(last=False)

    def record_success(self, key: str) -> None:
        self._records.pop(key, None)

    def tracked_keys(self) -> int:
        return len(self._records)

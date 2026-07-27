"""Varsayılan zaman kaynağı ve uyutucu.

`Clock` ve `Sleeper` protokollerinin stdlib tabanlı uygulamaları. Testler kendi
sahtesini verebilsin diye süre ölçen ya da bekleyen kod doğrudan `time`/`asyncio`
çağırmaz.
"""

from __future__ import annotations

import asyncio
import time


class SystemClock:
    """Gerçek sistem saati (monoton)."""

    def monotonic(self) -> float:
        return time.perf_counter()

    def now(self) -> float:
        return time.time()


class SystemSleeper:
    """Gerçek bekleme. İptal edilebilir olması önemlidir: kullanıcı turu keserse
    34 saniyelik bir gecikmenin ortasında takılı kalınmaz — `asyncio.sleep` iptal
    sinyalini geçirir."""

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

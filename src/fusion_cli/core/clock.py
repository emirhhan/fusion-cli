"""Varsayılan zaman kaynağı.

`Clock` protokolünün stdlib tabanlı uygulaması. Testler kendi sahte saatini
verebilsin diye süre ölçen kod doğrudan `time` modülünü çağırmaz.
"""

from __future__ import annotations

import time


class SystemClock:
    """Gerçek sistem saati (monoton)."""

    def monotonic(self) -> float:
        return time.perf_counter()

    def now(self) -> float:
        return time.time()

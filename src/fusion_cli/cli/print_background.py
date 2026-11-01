"""`-p` tur sonunda arka plan işini bekleme (#316).

Claude Code'da `claude -p` turu bitince Claude'un başlattığı arka plan alt ajanlarını bekler;
beş saniye sonra stderr'e `Waiting for background work to finish` yazar. Tavan toplam süre
değil, KESİNTİSİZ BOŞTA bekleme süresidir (varsayılan 10 dk,
`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`; `0` tavansız bekler). Fusion'da etkinlik, koşunun olay
veriyolundan geçen her olaydır (alt ajanların model/araç olayları dahil): olay geldikçe boşta
sayaç sıfırlanır.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar

from ..ui import print_messages as texts

if TYPE_CHECKING:
    from ..engines.agent.child_runs import ChildRuns

#: Arka plan işi beklenirken stderr bildirimi bu kadar sonra yazılır (Claude: 5 sn).
BG_NOTICE_DELAY_S = 5.0
#: Boşta bekleme tavanı (ms); Claude ile aynı ortam değişkeni ve varsayılan (10 dk).
BG_WAIT_CEILING_ENV = "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"
BG_WAIT_CEILING_DEFAULT_MS = 600_000

_T = TypeVar("_T")


class ActivityClock:
    """Olay veriyolu alıcısı: son etkinliğin zamanını tutar (boşta süre ölçümü için)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.last = clock()

    def handle(self, _event: object) -> None:
        self.last = self._clock()

    def idle_s(self) -> float:
        return max(0.0, self._clock() - self.last)


def bg_wait_ceiling_s() -> float | None:
    """Boşta bekleme tavanı (sn); `0` tavansız demektir (None)."""
    raw = os.environ.get(BG_WAIT_CEILING_ENV, "").strip()
    try:
        value = int(raw) if raw else BG_WAIT_CEILING_DEFAULT_MS
    except ValueError:
        value = BG_WAIT_CEILING_DEFAULT_MS
    if value <= 0:
        return None
    return value / 1000


async def wait_background(
    child_runs: ChildRuns,
    notify: Callable[[str], None],
    *,
    delay_s: float = BG_NOTICE_DELAY_S,
    activity: ActivityClock | None = None,
) -> None:
    """Tur bitince başlatılmış arka plan alt ajanlarını boşta tavanına kadar bekle.

    Tavan dolunca kalan iş durdurulur ve kısmi sonucu düşer (Claude ile aynı).
    """
    if not child_runs.active_count:
        return
    clock = activity or ActivityClock()
    clock.handle(None)  # boşta süre turun bitişinden sayılır
    drain = asyncio.ensure_future(child_runs.drain())
    ceiling = bg_wait_ceiling_s()
    started = time.monotonic()
    notified = False
    while not drain.done():
        idle_left = None if ceiling is None else ceiling - clock.idle_s()
        if idle_left is not None and idle_left <= 0:
            drain.cancel()
            await child_runs.close()
            return
        notice_left = None if notified else delay_s - (time.monotonic() - started)
        if notice_left is not None and notice_left <= 0:
            notify(texts.PRINT_WAITING_BACKGROUND)
            notified = True
            continue
        steps = [value for value in (idle_left, notice_left) if value is not None]
        await asyncio.wait({drain}, timeout=min(steps) if steps else None)
    if not drain.cancelled() and drain.exception() is not None:
        notify(str(drain.exception()))


async def run_then_wait(
    coro: Coroutine[Any, Any, _T],
    child_runs: ChildRuns,
    notify: Callable[[str], None],
    activity: ActivityClock,
) -> _T:
    """Turu koş; sonra başlattığı arka plan alt ajanlarını boşta tavanıyla bekle."""
    outcome = await coro
    await wait_background(child_runs, notify, activity=activity)
    return outcome

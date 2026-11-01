"""`fusion agent` (tek atış) arka plan işlerini bekler ve bildirimleriyle sürer (#335).

Claude Code (headless, interactive-mode › How backgrounding works): `-p` koşusu çıkmadan önce
ana konuşmanın arka plan komutunu bekler — komut çıkana ya da süre sınırına ulaşana kadar
(gözetimsiz sınır: metin istemde 10 dk, `job_lifetime`). Biten iş ve `monitor` satırı
bildirimi modele yeni bir tur olarak gider; model yeni iş başlatırsa yine beklenir.
`--bare` ve `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` arka plan işini kapatır, beklenmez.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from ..core.background_events import BackgroundEvents
from ..core.types import Message
from ..tools import job_lifetime
from ..ui import messages

__all__ = ["MAX_BACKGROUND_FOLLOWUPS", "run_with_background"]

#: Bildirimle açılan ek turların tavanı (iş başlatıp duran döngüye karşı).
MAX_BACKGROUND_FOLLOWUPS = 20
#: İş bittikten sonra bildirim iş parçacığına tanınan süre (saniye).
_SETTLE_S = 0.3

Turn = Callable[[str, Sequence[Message]], Awaitable[object]]


async def run_with_background(
    turn: Turn, task: str, events: BackgroundEvents, *, enabled: bool
) -> object:
    """İlk turu çalıştır; süren arka plan işi varsa bitmesini bekle ve bildirimle sür."""
    outcome = await turn(task, ())
    if not enabled:
        return outcome
    for _ in range(MAX_BACKGROUND_FOLLOWUPS):
        if not job_lifetime.running_owned() and not events.pending:
            return outcome
        await asyncio.to_thread(job_lifetime.wait_owned, None)
        await asyncio.sleep(_SETTLE_S)
        # Yalnız YENİ olay tur açar: turu boşaltmadan biten olay sonsuz döngü kurmasın.
        if not events.claim_wake():
            return outcome
        history = tuple(getattr(outcome, "messages", ()) or ())
        outcome = await turn(messages.BACKGROUND_WAKE, history)
    return outcome

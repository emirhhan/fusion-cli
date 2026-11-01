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
#: Süren işlere bakma aralığı (saniye).
_POLL_S = 0.2

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
        await _wait_jobs()
        await asyncio.sleep(_SETTLE_S)
        # Yalnız YENİ olay tur açar: turu boşaltmadan biten olay sonsuz döngü kurmasın.
        if not events.claim_wake():
            return outcome
        history = tuple(getattr(outcome, "messages", ()) or ())
        outcome = await turn(messages.BACKGROUND_WAKE, history)
    return outcome


async def _wait_jobs() -> None:
    """Süren işler bitene kadar bekle (süre sınırı `job_lifetime._guard`'da).

    İş parçacığı yerine olay döngüsünde yoklanır: Ctrl+C görevi iptal edince bekleme hemen
    biter; `asyncio.run` kapanışta süren işin bitmesini bekleyen bir iş parçacığına takılmaz.
    """
    while job_lifetime.running_owned():  # noqa: ASYNC110 — süreç durumu, olay yok
        await asyncio.sleep(_POLL_S)

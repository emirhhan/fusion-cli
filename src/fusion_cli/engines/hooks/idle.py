"""`Notification(idle_prompt)`: girdi bekleyen oturum belirli süre boşta kalınca (P-009).

Claude Code, cevabını bitirip kullanıcıyı bekleyen oturum 60 sn boşta kalınca bu bildirimi
gönderir (masaüstü bildirimi, telefon mesajı betikleri buna bağlanır). Fusion'da her yüzey
(REPL, TUI, masaüstü oturumu) `watch_idle`'ı kendi meşguliyet sorgusuyla sahipli bir görev
olarak koşturur. Bildirim yalnız bir tur bittikten SONRA ve boşta kalış başına bir kez
gider; yeni tur sayacı sıfırlar. Süre `runtime.hook_idle_prompt_s` (0 = kapalı).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

from ...core.hooks.events import HookEvent, HookVerdict
from ...ui import messages
from .session import HookSession

#: Claude Code'un boşta bekleme bildirim türü.
IDLE_PROMPT = "idle_prompt"
#: Meşguliyet yoklama aralığı (sn).
IDLE_POLL_S = 1.0


@dataclass(slots=True)
class IdleTracker:
    """Meşgul → boşta geçişini izler; süre dolunca bir kez `True` döner (saf, saatsiz)."""

    idle_since: float | None = None
    notified: bool = False
    was_busy: bool = False

    def tick(self, *, busy: bool, now: float, limit_s: float) -> bool:
        if busy:
            self.was_busy, self.idle_since, self.notified = True, None, False
            return False
        if self.was_busy:
            self.was_busy, self.idle_since = False, now
        if self.idle_since is None or self.notified or limit_s <= 0:
            return False
        if now - self.idle_since < limit_s:
            return False
        self.notified = True
        return True


async def watch_idle(
    session: Callable[[], HookSession | None],
    is_busy: Callable[[], bool],
    limit_s: Callable[[], float],
    *,
    on_verdict: Callable[[HookVerdict], None] = lambda _verdict: None,
    poll_s: float = IDLE_POLL_S,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Süresiz döngü: sahibi iptal eder (`CancelledError` yutulmaz)."""
    tracker = IdleTracker()
    while True:
        await asyncio.sleep(poll_s)
        if not tracker.tick(busy=is_busy(), now=clock(), limit_s=limit_s()):
            continue
        hooks = session()
        if hooks is None or not hooks.has(HookEvent.NOTIFICATION):
            continue
        on_verdict(await hooks.notify(IDLE_PROMPT, messages.HOOKS_IDLE_NOTICE))

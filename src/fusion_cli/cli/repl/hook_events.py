"""Slash komutlarının kuyruğa aldığı kanca olaylarını gönderme (P-009, `CwdChanged`).

Komut işleyicileri eşzamanlıdır (`/cd` masaüstünde de aynı işleyiciyle koşar); kanca
süreci ise asenkron çalışır. İşleyici olayı `HookSession.defer` ile kuyruğa alır, komutu
çalıştıran yüzey (`loop.py`, `tui_loop.py`, `appserver/session.py`) hemen ardından bunu
çağırıp kancanın kullanıcıya dönük satırlarını (systemMessage, hata) gösterir.

`start_idle_watch`: iki REPL yüzeyinin boşta bekleme bildirimi gözcüsü (`idle_prompt`).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

from ...core.hooks.events import HookVerdict
from ...engines.hooks.idle import watch_idle
from ...ui import messages
from .state import ReplState


async def flush(state: ReplState) -> tuple[str, ...]:
    """Kuyruktaki kanca olaylarını gönder; kullanıcıya gösterilecek satırları döndür."""
    session = state.hook_session
    if session is None:
        return ()
    return verdict_lines(await session.flush_deferred())


def verdict_lines(verdict: HookVerdict) -> tuple[str, ...]:
    return (
        *(messages.HOOKS_SYSTEM.format(text=text) for text in verdict.system_messages),
        *(messages.HOOKS_ERROR.format(detail=detail) for detail in verdict.errors),
    )


def start_idle_watch(
    state: ReplState, is_busy: Callable[[], bool], emit: Callable[[str], None]
) -> asyncio.Future[None]:
    """`Notification(idle_prompt)` gözcüsü (P-009); sahibi `stop_idle_watch` ile kapatır."""

    def _limit() -> float:
        return float(getattr(state.config.runtime, "hook_idle_prompt_s", 0) or 0)

    def _show(verdict: HookVerdict) -> None:
        for line in verdict_lines(verdict):
            emit(line)

    return asyncio.ensure_future(
        watch_idle(lambda: state.hook_session, is_busy, _limit, on_verdict=_show)
    )


async def stop_idle_watch(task: asyncio.Future[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

"""Açılışta arka planda `SessionStart` (#111): masaüstü sekmesi oturumu açınca.

Claude Code SessionStart kancalarını oturum açılırken arka planda çalıştırır; ilk cevap
onları bekler. REPL/TUI açılışta doğrudan bekler (`cli/repl/hook_open.py`); masaüstünde
`oturum.baslat` beklenmeden döner, kanca arka planda koşar ve ilk kök tur
(`hook_bridge.user_prompt_submit`) `settle_opening` ile sonucu bekler: bağlam ilk isteme,
`systemMessage`/hatalar ilk turun anlatımına gider.
"""

from __future__ import annotations

import asyncio
import contextlib

from ...core.hooks.events import HookEvent, HookVerdict
from .session import NO_VERDICT, HookSession


def open_soon(session: HookSession) -> bool:
    """SessionStart tanımlıysa ve oturum açılmadıysa arka planda başlat; başladıysa `True`."""
    session.refresh()
    if session.started or not session.has(HookEvent.SESSION_START):
        return False
    pending = session.opening
    if isinstance(pending, asyncio.Task) and not pending.done():
        return False
    try:
        session.opening = asyncio.get_running_loop().create_task(session.open())
    except RuntimeError:
        return False
    return True


async def settle_opening(session: HookSession) -> HookVerdict:
    """Arka plandaki açılışı bekle; kararı bir kez döndür (sonrakiler boş)."""
    task, session.opening = session.opening, None
    if not isinstance(task, asyncio.Task):
        return NO_VERDICT
    with contextlib.suppress(asyncio.CancelledError):
        return await task
    return NO_VERDICT

"""Slash komutlarının kuyruğa aldığı kanca olaylarını gönderme (P-009, `CwdChanged`).

Komut işleyicileri eşzamanlıdır (`/cd` masaüstünde de aynı işleyiciyle koşar); kanca
süreci ise asenkron çalışır. İşleyici olayı `HookSession.defer` ile kuyruğa alır, komutu
çalıştıran yüzey (`loop.py`, `tui_loop.py`, `appserver/session.py`) hemen ardından bunu
çağırıp kancanın kullanıcıya dönük satırlarını (systemMessage, hata) gösterir.
"""

from __future__ import annotations

from ...core.hooks.events import HookVerdict
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

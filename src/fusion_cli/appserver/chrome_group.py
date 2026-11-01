"""Masaüstü sohbetinde Chrome oturum sekme grubunun kapanışı (#436).

Claude in Chrome: `/clear` oturumun sekme grubunu sayfalarıyla kapatır; oturum değişince
(Claude'da `/resume`) ve çıkışta grup yalnız boş yeni sekmelerden oluşuyorsa kapanır.
Masaüstünde `/clear` sırasında tur sürüyorsa grup yalnız boşsa kapanır: süren işin açık
sekmesi elinden alınmaz. Kapanış arka plana bırakılır; eklenti bağlı değilse hiçbir şey
yapmaz, Chrome'u açmaz (`ChromeBridge.close_tab_group`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Protocol


class GroupCloser(Protocol):
    def close_tab_group(self, *, only_empty: bool) -> Awaitable[int]: ...


#: Arka plandaki kapanış görevleri: çöp toplayıcı bitmeden silmesin diye tutulur.
_PENDING: set[asyncio.Task[int]] = set()


def schedule_group_close(bridge: GroupCloser | None, *, only_empty: bool) -> None:
    """Grup kapanışını arka plana bırak; döngü yoksa ya da köprü yoksa bir şey yapma."""
    if bridge is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_close(bridge, only_empty=only_empty))
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)


async def _close(bridge: GroupCloser, *, only_empty: bool) -> int:
    return await bridge.close_tab_group(only_empty=only_empty)

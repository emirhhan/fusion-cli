"""Açıldığı görevde süre sınırlı MCP kaynak temizliği."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack


async def close_failed_stack(
    stack: AsyncExitStack, error: BaseException, timeout_seconds: float
) -> BaseException | None:
    """Başarısız bağlantının kaynaklarını kapat; asıl hatayı döndür, dış iptalde None.

    SDK taşıma görev grubundaki hatayı (ör. OAuth kaydı reddi) bekleyen
    `initialize` çağrısını İPTAL ederek bildirir; asıl hata ancak görev grubu
    kapanırken `ExceptionGroup` içinde görünür. Ölçüldü (Meta Ads MCP): bu iptal
    `except Exception`'dan kaçıyor, giriş görevini düşürüyor ve arayüz sonsuza
    dek "Giriş bekleniyor" gösteriyordu. Görevin kendisi dışarıdan iptal
    edildiyse iptal yutulmaz.
    """
    try:
        async with asyncio.timeout(timeout_seconds):
            await stack.aclose()
    except Exception as close_error:  # görev grubu asıl hatayı kapanışta verir
        error = close_error
    if isinstance(error, Exception):
        return error
    task = asyncio.current_task()
    is_internal_cancel = isinstance(error, asyncio.CancelledError) and (
        task is None or task.cancelling() == 0
    )
    return error if is_internal_cancel else None


async def wait_owned_task(task: asyncio.Task[None] | None, timeout_seconds: float) -> None:
    """Yığını başka görevde kapatma; sahibine kapanış süresi ve iptal sinyali ver."""
    import logging

    if task is None:
        return
    if not task.done():
        done, _ = await asyncio.wait({task}, timeout=max(0.0, timeout_seconds))
        if not done:
            task.cancel()
            await asyncio.sleep(0)
            logging.getLogger(__name__).warning("MCP gözetmeni kapanış süre sınırını aştı.")
    if task.done() and not task.cancelled():
        try:
            task.result()
        except Exception as error:
            logging.getLogger(__name__).warning(
                "MCP kapanışı başarısız", extra={"hata": type(error).__name__}
            )


async def drain_owned_tasks(
    tasks: set[asyncio.Task[None]],
    deadlines: dict[asyncio.Task[None], float],
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Kalan süre içinde kendi döngüsünün görevlerini bekle; bitmeyenin sahipliğini koru."""
    for task in tuple(tasks):
        if task.get_loop() is loop:
            await wait_owned_task(task, deadlines.get(task, loop.time()) - loop.time())
            if task.done():
                tasks.discard(task)
                deadlines.pop(task, None)

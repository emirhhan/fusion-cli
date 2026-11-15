"""Credential I/O: olay döngüsü dışında, süreç başına en fazla bir daemon worker.

Native Keychain çağrısı thread içinde kesilemez. İstek iptal olsa bile worker
gerçekten bitene dek yuvasını tutar; yeni denemeler ikinci thread üretmez.
Daemon oluşu kapanışın kilitli Keychain'i beklemesini önler. Burada sır cache'i yok.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")
_SLOT = threading.BoundedSemaphore(1)


class CredentialAccessError(RuntimeError):
    """Ham native/credential hata içeriğini dışarı taşımayan erişim hatası."""


async def resolve_credential(operation: Callable[[], _T]) -> _T:
    """Çağıranın async timeout/iptalini koru, sınırsız bekleyen worker üretme."""
    # Semaphore farklı event loop'ları da kapsar; bir loop'a bağlı asyncio.Event değil.
    while not _SLOT.acquire(blocking=False):  # noqa: ASYNC110
        await asyncio.sleep(0.01)

    loop = asyncio.get_running_loop()
    future: asyncio.Future[_T] = loop.create_future()

    def settle(value: _T | None, error: CredentialAccessError | None) -> None:
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(value)  # type: ignore[arg-type]

    def work() -> None:
        value: _T | None = None
        error = None
        try:
            value = operation()
        except BaseException as caught:
            # Yerel API hata metni hesap/credential ayrıntısı içerebilir.
            error = CredentialAccessError(
                f"Kimlik deposuna erişilemedi ({type(caught).__name__}); "
                "anahtarlık erişimini kontrol et."
            )
        finally:
            _SLOT.release()
        with contextlib.suppress(RuntimeError):  # Çağıranın döngüsü kapanmış olabilir.
            loop.call_soon_threadsafe(settle, value, error)

    worker = threading.Thread(target=work, name="fusion-credential", daemon=True)
    try:
        worker.start()
    except Exception:
        _SLOT.release()
        raise
    return await future

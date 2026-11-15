"""Uzun, iptal edilemeyen engelleyici işi daemon thread'de çalıştır.

`asyncio.to_thread` varsayılan executor'ı kullanır: o thread'ler süreç çıkışında BEKLENİR.
90 sn'ye kadar sürebilen ağ doğrulaması (NIM araç sondası) kapanışı ve süreç çıkışını o kadar
geciktirirdi (S2-22). Daemon thread çıkışta beklenmez; sonuç ya da hata, görev iptal
edilmişse sessizce atılır.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_in_daemon_thread(function: Callable[[], T]) -> T:
    """Argümansız `function`'ı daemon thread'de çalıştır ve sonucunu bekle."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[T] = loop.create_future()

    def settle(result: T | None, error: BaseException | None) -> None:
        if future.done():
            return  # çağıran görev iptal edildi
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)  # type: ignore[arg-type]

    def work() -> None:
        result: T | None = None
        error: BaseException | None = None
        try:
            result = function()
        except BaseException as caught:
            error = caught
        try:
            loop.call_soon_threadsafe(settle, result, error)
        except RuntimeError:
            return  # döngü kapandı: sonuç zaten kimsenin işine yaramaz

    threading.Thread(target=work, name="fusion-daemon-work", daemon=True).start()
    return await future

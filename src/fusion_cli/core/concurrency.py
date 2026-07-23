"""Zaman bütçeli paralel toplama.

Fusion motorunun "yavaş aday tüm turu kilitlemesin" davranışı buradadır ve
bilinçli olarak GENERİKTİR: ne modelden ne sağlayıcıdan haberi vardır, yalnızca
awaitable üretecleri alır. Böylece ağ olmadan, sahte gecikmelerle test edilebilir
ve ileride başka paralel işler (araç çağrıları, alt-ajanlar) aynı davranışı
tekrar yazmadan kullanabilir.

Üç zaman kuralı birlikte çalışır:

- **grace** — yeterli sayıda başarı geldikten sonra yavaşlara verilen son süre.
- **hard cap** — İLK başarıdan itibaren mutlak üst sınır; soğuk bir uç turu
  süresiz uzatamaz.
- İkisi de dolmadıysa iş bitene kadar beklenir.

Zamanı dolduran işler iptal edilir; toplanan sonuçlar bitiş SIRASIYLA döner.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from typing import TypeVar

T = TypeVar("T")


async def gather_with_cutoff(
    factories: Sequence[Callable[[], Awaitable[T]]],
    *,
    is_success: Callable[[T], bool],
    enough_success: int,
    grace_s: float,
    hard_cap_s: float,
    on_result: Callable[[T], None] | None = None,
) -> list[T]:
    """Hepsini paralel başlat, zaman bütçesi dolunca elde olanlarla devam et.

    `enough_success` kadar başarılı sonuç geldiğinde kalanlara `grace_s` süre tanınır.
    İlk başarıdan itibaren toplam bekleme `hard_cap_s`'i aşamaz.
    """
    if not factories:
        return []

    loop = asyncio.get_running_loop()
    tasks = {asyncio.ensure_future(factory()) for factory in factories}
    results: list[T] = []
    grace_deadline: float | None = None
    hard_deadline: float | None = None

    try:
        while tasks:
            timeout = _remaining(loop.time(), grace_deadline, hard_deadline)
            if timeout is not None and timeout <= 0:
                break

            done, tasks = await asyncio.wait(
                tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                break  # grace ya da mutlak üst sınır doldu

            for task in done:
                result = task.result()
                results.append(result)
                if on_result is not None:
                    on_result(result)

            successes = sum(1 for result in results if is_success(result))
            if hard_deadline is None and successes >= 1:
                hard_deadline = loop.time() + hard_cap_s
            if grace_deadline is None and successes >= enough_success:
                grace_deadline = loop.time() + grace_s
    finally:
        await _cancel(tasks)

    return results


def _remaining(now: float, *deadlines: float | None) -> float | None:
    """En yakın son tarihe kalan süre; hiç son tarih yoksa None (süresiz bekle)."""
    pending = [deadline - now for deadline in deadlines if deadline is not None]
    return min(pending) if pending else None


async def _cancel(tasks: set[asyncio.Task[T]]) -> None:
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


class BackgroundTasks:
    """Turu bekletmeden çalışacak işler.

    Ders çıkarımı gibi öğrenme işleri kullanıcının bir sonraki komutunu beklet-
    memelidir; ama başıboş da bırakılamaz — sahipsiz bir task çöp toplayıcı ya da
    olay döngüsünün kapanmasıyla sessizce iptal olur ve öğrenme kaybolur.

    Bu yüzden işler burada TUTULUR ve oturum kapanırken `drain()` ile beklenir.
    Hatalar yutulmaz; `failures` üzerinden görünür kalır.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()
        self.failures: list[str] = []

    def spawn(self, coroutine: Coroutine[object, object, None]) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._finish)

    async def drain(self) -> None:
        """Bekleyen tüm işleri tamamla."""
        while self._tasks:
            pending = tuple(self._tasks)
            await asyncio.gather(*pending, return_exceptions=True)

    @property
    def pending(self) -> int:
        return len(self._tasks)

    def _finish(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.failures.append(f"{type(error).__name__}: {error}")

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
from collections.abc import Awaitable, Callable, Sequence
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

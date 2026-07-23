"""Olay veriyolu — çıktı çakışmasının yapısal çözümü.

Tasarım kararları ve gerekçeleri:

- `publish()` senkrondur, asla bloklamaz ve asla hata fırlatmaz. Motor kodu olay
  yayınlarken yavaşlamaz; yayınlamak "gönder ve unut"tur.
- Olaylar TEK bir tüketici tarafından, geldikleri SIRAYLA dağıtılır. Eski projede
  iki ayrı akış aynı anda konsola yazdığı için satırlar birbirini bölüyordu; burada
  dinleyiciye aynı anda ikinci bir olay ulaşamaz.
- Bir dinleyicinin hatası diğerlerini ve turu etkilemez; yakalanır ve teşhis için
  `failures` listesine yazılır (sessizce yutulmaz).
- Veriyolu kapanırken kuyruk BOŞALANA kadar beklenir; tur bitti diye son olaylar
  kaybolmaz.
"""

from __future__ import annotations

import asyncio
from types import TracebackType

from ..core.events import Event, EventSink


class EventBus:
    """Olayları sırayla dinleyicilere dağıtan veriyolu.

    `async with` içinde kullanılır: girişte tüketici başlar, çıkışta kuyruk boşaltılıp
    tüketici durdurulur.
    """

    def __init__(self) -> None:
        self._sinks: list[EventSink] = []
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._consumer: asyncio.Task[None] | None = None
        self.failures: list[str] = []

    def subscribe(self, sink: EventSink) -> None:
        """Dinleyici ekle. Olaylar eklenme sırasına göre iletilir."""
        self._sinks.append(sink)

    def publish(self, event: Event) -> None:
        """Olayı kuyruğa koy. Bloklamaz; veriyolu kapalıysa bile kayıp olmaz."""
        self._queue.put_nowait(event)

    async def __aenter__(self) -> EventBus:
        self._consumer = asyncio.create_task(self._consume())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.drain()
        if self._consumer is not None:
            self._consumer.cancel()
            await asyncio.gather(self._consumer, return_exceptions=True)
            self._consumer = None

    async def drain(self) -> None:
        """Kuyruktaki tüm olaylar dağıtılana kadar bekle."""
        await self._queue.join()

    async def _consume(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                self._dispatch(event)
            finally:
                self._queue.task_done()

    def _dispatch(self, event: Event) -> None:
        for sink in self._sinks:
            try:
                sink.handle(event)
            # Geniş yakalama bilinçli: bu bir sınır noktasıdır, bir dinleyicinin
            # hatası turu düşüremez. Hata yutulmaz, `failures` üzerinden görünür.
            except Exception as exc:
                self.failures.append(f"{type(sink).__name__}: {type(exc).__name__}: {exc}")

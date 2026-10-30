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
import threading
from types import TracebackType

from ..core.events import Event, EventSink

#: `failures` listesinde tutulan en son hata sayısı.
_MAX_FAILURES = 200


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
        self._closed = False
        #: Tüketicinin döngüsü ve iş parçacığı: araçlar `asyncio.to_thread` içinden olay
        #: yayınlayabilir; `Queue.put_nowait` iş parçacığı güvenli değildir.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: int | None = None

    def subscribe(self, sink: EventSink) -> None:
        """Dinleyici ekle. Olaylar eklenme sırasına göre iletilir."""
        self._sinks.append(sink)

    def publish(self, event: Event) -> None:
        """Olayı kuyruğa koy. Bloklamaz; veriyolu kapalıysa bile kayıp olmaz."""
        if self._closed:
            # Oturumun sahip olduğu öğrenme işi turdan sonra da olay üretebilir.
            # Aynı dinleyiciler muhasebe/denetimi sürdürür; sahipsiz kuyruk açılmaz.
            self._dispatch(event)
        elif (
            self._loop is not None
            and self._loop_thread != threading.get_ident()
            and not self._loop.is_closed()
        ):
            # Başka iş parçacığından gelen olay döngüye güvenle devredilir. Ölçüldü (30 Ekim):
            # doğrudan put_nowait tüketiciyi uyandırmayabilir / kuyruğu bozabilir.
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        else:
            self._queue.put_nowait(event)

    async def __aenter__(self) -> EventBus:
        self._closed = False
        self._loop = asyncio.get_running_loop()
        self._loop_thread = threading.get_ident()
        self._consumer = asyncio.create_task(self._consume())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        while True:
            await self.drain()
            # join() uyandırıldıktan sonra planlanmış bir yayın kuyruğa girebilir.
            # Boşluk kontrolü ve kapatma arasında await yoktur; sıra korunur.
            if self._queue.empty():
                self._closed = True
                break
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
                # Üst sınırsız büyümesin (kırık boru her olayda bir kayıt ekleyebilir).
                del self.failures[:-_MAX_FAILURES]

"""Kayıttan çalan sağlayıcı — canlı bir koşuyu ağsız yeniden üretir.

Ajan hatalarını tahminle ayıklamak pahalıdır: 5-6 Eylül koşularında bir
başarısızlığı anlamak için transkriptler elle okundu ve o koşu bir daha aynen
üretilemedi. İz zaten diskte duruyor; oradaki model yanıtlarını sırasıyla geri
oynatan bir sağlayıcı, aynı başarısızlığı ağ olmadan ve deterministik biçimde
tekrar üretir. Böylece bir hata, regresyon testine dönüşebilir.

Kayıt bittiğinde UYDURMAZ: açıkça "kayıt tükendi" der. Uydurulmuş bir devam,
tekrar oynatmanın tek değerini — birebirliği — yok ederdi.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from ..core.events import Event, ModelCallFinished
from ..core.types import CompletionRequest, ModelResult, StreamDone, StreamItem, TextChunk


def recorded_results(events: Sequence[Event]) -> tuple[ModelResult, ...]:
    """İzdeki model yanıtlarını kayıt sırasıyla çıkar."""
    return tuple(
        event.result
        for event in events
        if isinstance(event, ModelCallFinished) and isinstance(event.result, ModelResult)
    )


class ReplayProvider:
    """Kayıtlı yanıtları sırayla döndüren sağlayıcı."""

    def __init__(self, results: Sequence[ModelResult], *, label: str = "replay") -> None:
        self._results = tuple(results)
        self._label = label
        self._index = 0

    @property
    def label(self) -> str:
        return self._label

    async def complete(self, request: CompletionRequest) -> ModelResult:
        del request  # Tekrar oynatma isteğe BAKMAZ: kayıt neyse odur.
        if self._index >= len(self._results):
            return ModelResult(
                name=self._label,
                model=self._label,
                text="",
                latency_ms=0,
                ok=False,
                error="kayıt tükendi: izde bu çağrı için yanıt yok",
            )
        result = self._results[self._index]
        self._index += 1
        return result

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        result = await self.complete(request)
        if result.text:
            yield TextChunk(result.text)
        yield StreamDone(result)

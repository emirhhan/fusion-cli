"""Hedged sağlayıcı — N sağlayıcıyı YARIŞTIRIR, ilk başarılı yanıt kazanır.

Neden dekoratör: eski projede yarıştırma mantığı `acomplete` fonksiyonunun içine
gömülüydü ve streaming için ayrıca kopyalanmıştı. Burada tek bir generic sarmalayıcı
hem `complete` hem `stream` için çalışır ve sarmaladığı şeyin ne olduğunu bilmez;
yeni bir sağlayıcı eklendiğinde dayanıklılık davranışı bedava gelir.

Davranış:
- Tüm alt sağlayıcılar AYNI ANDA başlatılır; gecikme = min(hepsi), toplam değil.
- İlk başarılı yanıt kazanır; kalanlar iptal edilir.
- Hiçbiri başaramazsa hata fırlatılmaz; tüm hataları birleştiren `ok=False` sonuç döner.
- Akışta ilk ÇIKTI ÜRETEN akış kazanır (yalnız bağlantı açan değil): soğuk ya da hemen
  hata veren bir uç turu kilitleyemez.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from ..core.errors import ProviderError
from ..core.protocols import LlmProvider
from ..core.types import CompletionRequest, ModelResult, StreamDone, StreamItem

#: Bir akışın ilk öğesi: (sıra numarası, öğe). Öğe None ise akış hiç üretmeden bitti.
_Opened = tuple[int, StreamItem | None]


class HedgedProvider:
    """Birden çok sağlayıcıyı yarıştıran sağlayıcı."""

    def __init__(self, providers: Sequence[LlmProvider], *, role: str) -> None:
        if not providers:
            raise ProviderError(f"'{role}' için tanımlı model yok.")
        self._providers = tuple(providers)
        self._role = role

    @property
    def label(self) -> str:
        return " | ".join(provider.label for provider in self._providers)

    async def complete(self, request: CompletionRequest) -> ModelResult:
        if len(self._providers) == 1:
            return await self._providers[0].complete(request)

        tasks = [asyncio.create_task(provider.complete(request)) for provider in self._providers]
        failures: list[ModelResult] = []
        try:
            for finished in asyncio.as_completed(tasks):
                result = await finished
                if result.ok:
                    return result
                failures.append(result)
        finally:
            await _cancel_all(tasks)
        return self._all_failed(failures)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        if len(self._providers) == 1:
            async for item in self._providers[0].stream(request):
                yield item
            return

        streams = [provider.stream(request) for provider in self._providers]
        openers = [
            asyncio.create_task(_open(index, stream)) for index, stream in enumerate(streams)
        ]
        winner: tuple[int, StreamItem] | None = None
        failures: list[ModelResult] = []

        try:
            for finished in asyncio.as_completed(openers):
                index, opened = await finished
                if opened is None:
                    continue
                if isinstance(opened, StreamDone) and not opened.result.ok:
                    failures.append(opened.result)
                    continue
                winner = (index, opened)
                break
        finally:
            await _cancel_all(openers)

        if winner is None:
            await _close_all(streams)
            yield StreamDone(self._all_failed(failures))
            return

        winning_index, first_item = winner
        await _close_all([s for position, s in enumerate(streams) if position != winning_index])

        yield first_item
        if isinstance(first_item, StreamDone):
            return
        async for item in streams[winning_index]:
            yield item

    def _all_failed(self, failures: Sequence[ModelResult]) -> ModelResult:
        errors = "; ".join(failure.error or "bilinmeyen hata" for failure in failures)
        return ModelResult(
            name=self._role,
            model=self._providers[0].label,
            text="",
            latency_ms=max((failure.latency_ms for failure in failures), default=0),
            ok=False,
            error=errors or "tüm sağlayıcılar yanıt veremedi",
        )


async def _open(index: int, stream: AsyncIterator[StreamItem]) -> _Opened:
    """Akıştan ilk öğeyi çek; akış hiç üretmeden biterse None döndür."""
    try:
        return index, await anext(stream)
    except StopAsyncIteration:
        return index, None


async def _cancel_all(tasks: Sequence[asyncio.Task[Any]]) -> None:
    pending = [task for task in tasks if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def _close_all(streams: Sequence[AsyncIterator[StreamItem]]) -> None:
    """Kaybeden akışları kapat; arkada açık bağlantı bırakma."""
    for stream in streams:
        closer = getattr(stream, "aclose", None)
        if closer is None:
            continue
        # Kaybeden akışın kapanış hatası turu etkilemez; bilinçli olarak yutulur.
        try:
            await closer()
        except Exception:
            continue

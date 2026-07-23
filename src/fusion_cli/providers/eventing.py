"""Olay yayınlayan sağlayıcı sarmalayıcısı.

Sağlayıcı çağrılarının yaşam döngüsünü olaya çevirir. Sarmaladığı sağlayıcının ne
olduğunu bilmez; `LiteLlmProvider`, `HedgedProvider` ya da testteki sahte sağlayıcı —
hepsi için aynı şekilde çalışır.

Bu sayede motor katmanı "ilerlemeyi kullanıcıya nasıl göstereceğim" sorusunu hiç
sormaz; yalnızca sağlayıcıyı çağırır.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..core.events import (
    Channel,
    EventPublisher,
    ModelCallFinished,
    ModelCallStarted,
    TokenReceived,
)
from ..core.protocols import LlmProvider
from ..core.types import CompletionRequest, ModelResult, StreamDone, StreamItem, TextChunk


class EventingProvider:
    """Alt sağlayıcının çağrılarını olay olarak yayınlar."""

    def __init__(
        self,
        inner: LlmProvider,
        *,
        publisher: EventPublisher,
        role: str,
        channel: Channel = Channel.MAIN,
    ) -> None:
        self._inner = inner
        self._publisher = publisher
        self._role = role
        self._channel = channel

    @property
    def label(self) -> str:
        return self._inner.label

    async def complete(self, request: CompletionRequest) -> ModelResult:
        self._publisher.publish(ModelCallStarted(role=self._role, model=self._inner.label))
        result = await self._inner.complete(request)
        self._publisher.publish(ModelCallFinished(role=self._role, result=result))
        return result

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        self._publisher.publish(ModelCallStarted(role=self._role, model=self._inner.label))
        async for item in self._inner.stream(request):
            if isinstance(item, TextChunk):
                self._publisher.publish(TokenReceived(channel=self._channel, text=item.text))
            elif isinstance(item, StreamDone):
                self._publisher.publish(ModelCallFinished(role=self._role, result=item.result))
            yield item

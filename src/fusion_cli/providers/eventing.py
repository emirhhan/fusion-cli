"""Olay yayınlayan sağlayıcı sarmalayıcısı.

Sağlayıcı çağrılarının yaşam döngüsünü olaya çevirir. Sarmaladığı sağlayıcının ne
olduğunu bilmez; `LiteLlmProvider`, `FallbackProvider` ya da testteki sahte sağlayıcı —
hepsi için aynı şekilde çalışır.

Bu sayede motor katmanı "ilerlemeyi kullanıcıya nasıl göstereceğim" sorusunu hiç
sormaz; yalnızca sağlayıcıyı çağırır.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from uuid import uuid4

from ..core import display_filter
from ..core.events import (
    Channel,
    EventPublisher,
    ModelCallAbandoned,
    ModelCallFinished,
    ModelCallPurpose,
    ModelCallStarted,
    TierDegraded,
    TokenReceived,
)
from ..core.protocols import LlmProvider
from ..core.tier import tier_mismatch
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
        background: bool = False,
        purpose: ModelCallPurpose = "other",
        call_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._call_id_factory = call_id_factory or (lambda: uuid4().hex)
        self._inner = inner
        self._publisher = publisher
        self._role = role
        self._channel = channel
        self._background = background
        self._purpose = purpose

    @property
    def label(self) -> str:
        return self._inner.label

    async def complete(self, request: CompletionRequest) -> ModelResult:
        call_id = self._call_id_factory()
        request = self._correlate_request(request, call_id)
        self._publisher.publish(self._started(call_id))
        try:
            result = await self._inner.complete(request)
        except (asyncio.CancelledError, Exception):
            # Zaman aşımı, kesilen yavaş aday ya da sözleşme dışı istisna: bitiş olayı
            # hiç gelmeyecek; açık kalan "çalışıyor" durumu kapatılır (P1-11).
            self._publish_abandoned(call_id)
            raise
        self._publish_finished(result, call_id)
        return result

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        call_id = self._call_id_factory()
        request = self._correlate_request(request, call_id)
        self._publisher.publish(self._started(call_id))
        finished = False
        # MessageDisplay kancası (#90): ana konuşmanın görünen metni satır partileriyle süzülür.
        display = display_filter.open_stream(call_id) if self._channel is Channel.MAIN else None
        try:
            async for item in self._inner.stream(request):
                if isinstance(item, TextChunk) and item.text:
                    # Boş parça yalnız canlılık işaretidir (bkz. `litellm_provider.stream`);
                    # arayüze olay olarak gitmez.
                    if display is None:
                        self._publish_text(item.text, item.provisional)
                    else:
                        self._publish_pieces(await display.feed(item.text, item.provisional))
                elif isinstance(item, StreamDone):
                    finished = True
                    if display is not None:
                        self._publish_pieces(await display.finish())
                    self._publish_finished(item.result, call_id)
                yield item
        except (asyncio.CancelledError, GeneratorExit, Exception):
            if not finished:
                self._publish_abandoned(call_id)
            raise

    def _publish_text(self, text: str, provisional: bool) -> None:
        self._publisher.publish(
            TokenReceived(channel=self._channel, text=text, provisional=provisional)
        )

    def _publish_pieces(self, pieces: list[display_filter.Piece]) -> None:
        for text, provisional in pieces:
            self._publish_text(text, provisional)

    @staticmethod
    def _correlate_request(request: CompletionRequest, call_id: str) -> CompletionRequest:
        """Tek lifecycle çağrı kimliğini mevcut uygulama turuna bağla."""
        if request.web_call_context is None:
            return request
        return replace(
            request, web_call_context=replace(request.web_call_context, model_call_id=call_id)
        )

    def _publish_abandoned(self, call_id: str) -> None:
        self._publisher.publish(
            ModelCallAbandoned(
                role=self._role,
                model=self._inner.label,
                background=self._background,
                call_id=call_id,
            )
        )

    def _started(self, call_id: str) -> ModelCallStarted:
        return ModelCallStarted(
            role=self._role, model=self._inner.label, background=self._background, call_id=call_id
        )

    def _publish_finished(self, result: ModelResult, call_id: str) -> None:
        self._publisher.publish(
            ModelCallFinished(
                role=self._role,
                result=result,
                background=self._background,
                call_id=call_id,
                requested_model=self._inner.label,
                purpose=self._purpose,
            )
        )
        # Yalnızca kullanıcı AÇIKÇA bir web kademesi seçtiyse (bkz. `core.tier`)
        # ve gözlenen bundan farklıysa yayınlanır; `/auto` durumunda sessizdir.
        beklenmeyen = tier_mismatch(result.model, result.served_by)
        if beklenmeyen:
            self._publisher.publish(
                TierDegraded(
                    model=result.model, expected_tier=beklenmeyen, served_by=result.served_by
                )
            )

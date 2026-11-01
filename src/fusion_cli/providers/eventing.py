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

from ..core.events import (
    Channel,
    EventPublisher,
    ModelCallAbandoned,
    ModelCallFinished,
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
        call_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._call_id_factory = call_id_factory or (lambda: uuid4().hex)
        self._inner = inner
        self._publisher = publisher
        self._role = role
        self._channel = channel
        self._background = background

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
        try:
            async for item in self._inner.stream(request):
                if isinstance(item, TextChunk) and item.text:
                    # Boş parça yalnız canlılık işaretidir (bkz. `litellm_provider.stream`);
                    # arayüze olay olarak gitmez.
                    self._publisher.publish(
                        TokenReceived(
                            channel=self._channel, text=item.text, provisional=item.provisional
                        )
                    )
                elif isinstance(item, StreamDone):
                    finished = True
                    self._publish_finished(item.result, call_id)
                yield item
        except (asyncio.CancelledError, GeneratorExit, Exception):
            if not finished:
                self._publish_abandoned(call_id)
            raise

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

"""Testlerde kullanılan sahte sağlayıcılar ve dinleyiciler (ağ erişimi YOK)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fusion_cli.core.events import Event
from fusion_cli.core.types import (
    CompletionRequest,
    ModelResult,
    StreamDone,
    StreamItem,
    TextChunk,
    TokenUsage,
)


class FakeProvider:
    """Verilen parçaları akıtan, istenirse geciken/başarısız olan sahte sağlayıcı."""

    def __init__(self, name, *, chunks=(), delay=0.0, ok=True, error=None):
        self._name = name
        self._chunks = tuple(chunks)
        self._delay = delay
        self._ok = ok
        self._error = error
        self.cancelled = False

    @property
    def label(self):
        return self._name

    def _result(self):
        return ModelResult(
            name=self._name,
            model=self._name,
            text="".join(self._chunks),
            latency_ms=1,
            ok=self._ok,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=len(self._chunks)),
            error=self._error,
        )

    async def complete(self, request: CompletionRequest) -> ModelResult:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self._result()

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if not self._ok:
            yield StreamDone(self._result())
            return
        for chunk in self._chunks:
            yield TextChunk(chunk)
        yield StreamDone(self._result())


class RecordingSink:
    """Gelen olayları sırayla biriktiren dinleyici."""

    def __init__(self):
        self.events: list[Event] = []

    def handle(self, event: Event) -> None:
        self.events.append(event)


class ExplodingSink:
    """Her olayda hata fırlatan dinleyici — veriyolunun dayanıklılığını sınar."""

    def handle(self, event: Event) -> None:
        raise RuntimeError("dinleyici patladı")


def request(**overrides) -> CompletionRequest:
    from fusion_cli.core.types import Message

    defaults = {
        "messages": (Message("user", "merhaba"),),
        "temperature": 0.0,
        "max_tokens": 16,
        "timeout_s": 5.0,
        "max_retries": 0,
    }
    defaults.update(overrides)
    return CompletionRequest(**defaults)

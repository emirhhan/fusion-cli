"""Bounded metadata-only observation; failures cannot change provider control flow."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from .events import ModelCallPurpose, ProviderCallDiagnostic, ProviderDiagnosticPhase

if TYPE_CHECKING:
    from .types import CompletionRequest

_COUNTER_MAX = 2**31 - 1
_TERMINAL = frozenset({"call_end", "call_cancelled", "call_error"})


class ProviderCallObserver:
    """One lifecycle scope shared by its wrapper/leaf invocations, never by payloads."""

    def __init__(
        self,
        emit: Callable[[ProviderCallDiagnostic], None],
        *,
        call_id: str,
        max_tokens: int,
        timeout_s: float,
        requested_sdk_retries: int,
        stream: bool,
        purpose: ModelCallPurpose,
        background: bool,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._emit = emit
        self._clock = clock
        self._call_id = call_id
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s
        self._requested_sdk_retries = requested_sdk_retries
        self._stream = stream
        self._purpose = purpose
        self._background = background
        self._started: float | None = None
        self._previous: ProviderDiagnosticPhase | None = None
        self._leaf_attempts = 0
        self._sdk_chunks = 0
        self._text_chunks = 0
        self._empty_chunks = 0
        self._leaf_chunks = 0
        self._closed = False
        self._disabled = False

    def phase(self, phase: ProviderDiagnosticPhase, *, wait_s: float | None = None) -> None:
        if self._closed or self._disabled:
            return
        try:
            now = self._clock()
            if self._started is None:
                self._started = now
            event = ProviderCallDiagnostic(
                call_id=self._call_id,
                phase=phase,
                previous_phase=self._previous,
                elapsed_ms=min(_COUNTER_MAX, max(0, int((now - self._started) * 1000))),
                leaf_attempts=self._leaf_attempts,
                sdk_chunks=self._sdk_chunks,
                sdk_text_chunks=self._text_chunks,
                sdk_empty_text_chunks=self._empty_chunks,
                max_tokens=self._max_tokens,
                timeout_s=self._timeout_s,
                requested_sdk_retries=self._requested_sdk_retries,
                stream=self._stream,
                purpose=self._purpose,
                background=self._background,
                wait_ms=None if wait_s is None else min(_COUNTER_MAX, max(0, int(wait_s * 1000))),
            )
            self._previous = phase
            self._closed = phase in _TERMINAL
            self._emit(event)
        except (Exception, asyncio.CancelledError):
            # Only observer work is protected; provider awaits/cancellation stay outside.
            self._disabled = True

    def leaf_enter(self) -> None:
        if self._closed or self._disabled:
            return
        self._leaf_attempts = min(_COUNTER_MAX, self._leaf_attempts + 1)
        self._leaf_chunks = 0
        self.phase("leaf_enter")

    def sdk_chunk(self, *, has_text: bool) -> None:
        if self._closed or self._disabled:
            return
        self._sdk_chunks = min(_COUNTER_MAX, self._sdk_chunks + 1)
        self._leaf_chunks = min(_COUNTER_MAX, self._leaf_chunks + 1)
        if has_text:
            self._text_chunks = min(_COUNTER_MAX, self._text_chunks + 1)
        else:
            self._empty_chunks = min(_COUNTER_MAX, self._empty_chunks + 1)
        if self._leaf_chunks == 1:
            self.phase("sdk_first_chunk")


def observe_phase(
    request: CompletionRequest, phase: ProviderDiagnosticPhase, *, wait_s: float | None = None
) -> None:
    if request.provider_observer is not None:
        request.provider_observer.phase(phase, wait_s=wait_s)

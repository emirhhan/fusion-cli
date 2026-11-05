"""A queued independent ping cannot establish that a silent primary is dead."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.core.types import ModelSpec, StreamDone
from fusion_cli.engines.agent import liveness, loop

from .fakes import model_result

SPEC = ModelSpec(name="agent", model="nvidia_nim/test")


@pytest.fixture(autouse=True)
def _short_probe(monkeypatch):
    monkeypatch.setattr(liveness, "CHECK_AFTER_S", 0.01)
    monkeypatch.setattr(liveness, "PING_TIMEOUT_S", 0.02)
    monkeypatch.setattr(liveness, "RECHECK_S", 0.01)


async def test_healthy_primary_finishes_after_queue_blocked_ping_times_out(monkeypatch):
    slot = asyncio.Lock()
    ping_finished = asyncio.Event()
    primary_cancelled = False

    class Primary:
        label = "primary"
        calls = 0

        async def stream(self, request):
            nonlocal primary_cancelled
            self.calls += 1
            async with slot:
                try:
                    await ping_finished.wait()
                    # Finish strictly after the watcher's timeout decision.
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    primary_cancelled = True
                    raise
                yield StreamDone(model_result("Tamamlandı: istenen iş yapıldı ve doğrulandı."))

    class QueuedPing:
        async def stream(self, request):
            try:
                async with slot:
                    yield StreamDone(model_result("tamam"))
            finally:
                ping_finished.set()

    primary = Primary()
    monkeypatch.setattr(liveness, "build_provider", lambda *a, **k: QueuedPing())
    result = None

    async def consume():
        nonlocal result
        async for item in primary.stream(None):
            result = item.result

    state = loop._State()
    await asyncio.wait_for(loop._consume_with_liveness(consume, SPEC, state), 1)

    assert result is not None and result.ok
    assert primary.calls == 1
    assert not primary_cancelled
    assert not state.unresponsive_reason


@pytest.mark.parametrize("probe_error", ["APITimeoutError: request timed out", None])
async def test_inconclusive_ping_result_preserves_primary(monkeypatch, probe_error):
    ping_done = asyncio.Event()
    completed = False

    class PingProvider:
        async def stream(self, request):
            ping_done.set()
            if probe_error:
                yield StreamDone(model_result("", ok=False, error=probe_error))

    async def consume():
        nonlocal completed
        await ping_done.wait()
        await asyncio.sleep(0.01)
        completed = True

    monkeypatch.setattr(liveness, "build_provider", lambda *a, **k: PingProvider())
    state = loop._State()
    await asyncio.wait_for(loop._consume_with_liveness(consume, SPEC, state), 1)

    assert completed
    assert not state.unresponsive_reason


async def test_unknown_probe_exception_preserves_primary(monkeypatch):
    probe_attempted = asyncio.Event()
    completed = False

    class PingProvider:
        async def stream(self, request):
            probe_attempted.set()
            raise ValueError("probe-specific setup failed")
            yield  # pragma: no cover

    async def consume():
        nonlocal completed
        await probe_attempted.wait()
        await asyncio.sleep(0.01)
        completed = True

    monkeypatch.setattr(liveness, "build_provider", lambda *a, **k: PingProvider())
    await asyncio.wait_for(loop._consume_with_liveness(consume, SPEC, loop._State()), 1)
    assert completed


async def test_unknown_ping_keeps_original_primary_deadline(monkeypatch):
    attempts = 0
    probe_closed = 0
    primary_closed = asyncio.Event()

    class PingProvider:
        async def stream(self, request):
            nonlocal attempts, probe_closed
            attempts += 1
            try:
                await asyncio.Event().wait()
                yield  # pragma: no cover
            finally:
                probe_closed += 1

    async def consume():
        try:
            async with asyncio.timeout(0.12):
                await asyncio.Event().wait()
        finally:
            primary_closed.set()

    monkeypatch.setattr(liveness, "build_provider", lambda *a, **k: PingProvider())
    state = loop._State()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(loop._consume_with_liveness(consume, SPEC, state), 1)

    assert primary_closed.is_set()
    assert attempts >= 2
    assert probe_closed == attempts
    assert not state.unresponsive_reason


async def test_user_cancel_closes_primary_and_inflight_ping(monkeypatch):
    probe_started = asyncio.Event()
    probe_closed = asyncio.Event()
    primary_closed = asyncio.Event()

    class PingProvider:
        async def stream(self, request):
            probe_started.set()
            try:
                await asyncio.Event().wait()
                yield  # pragma: no cover
            finally:
                probe_closed.set()

    async def consume():
        try:
            await asyncio.Event().wait()
        finally:
            primary_closed.set()

    monkeypatch.setattr(liveness, "build_provider", lambda *a, **k: PingProvider())
    task = asyncio.create_task(loop._consume_with_liveness(consume, SPEC, loop._State()))
    await asyncio.wait_for(probe_started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)

    assert primary_closed.is_set()
    assert probe_closed.is_set()


async def test_confirmed_connection_failure_still_cancels_primary(monkeypatch):
    primary_closed = asyncio.Event()

    class PingProvider:
        async def stream(self, request):
            raise ConnectionRefusedError("transport unavailable")
            yield  # pragma: no cover

    async def consume():
        try:
            await asyncio.Event().wait()
        finally:
            primary_closed.set()

    monkeypatch.setattr(liveness, "build_provider", lambda *a, **k: PingProvider())
    state = loop._State()
    with pytest.raises(TimeoutError, match="ConnectionRefusedError"):
        await asyncio.wait_for(loop._consume_with_liveness(consume, SPEC, state), 1)

    assert primary_closed.is_set()
    assert "ConnectionRefusedError" in state.unresponsive_reason


async def test_primary_chunk_during_probe_overrides_probe_failure():
    chunks = 0
    probe_done = asyncio.Event()

    async def ping():
        nonlocal chunks
        chunks = 1
        probe_done.set()
        return "confirmed transport failure on the independent ping"

    task = asyncio.create_task(liveness.watch(lambda: chunks, ping))
    try:
        await asyncio.wait_for(probe_done.wait(), 1)
        await asyncio.sleep(0)
        assert not task.done(), "A primary chunk is direct evidence of a live primary"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

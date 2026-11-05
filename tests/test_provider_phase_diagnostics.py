"""Provider phases describe observed boundaries without serializing model payloads."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.core.events import Channel
from fusion_cli.core.types import ModelResult
from fusion_cli.providers.eventing import EventingProvider
from fusion_cli.providers.litellm_provider import LiteLlmProvider

from .fakes import request


class Recorder:
    def __init__(self):
        self.events = []
        self.changed = asyncio.Event()

    def publish(self, event):
        self.events.append(event)
        self.changed.set()


def diagnostics(recorder):
    return [event for event in recorder.events if type(event).__name__ == "ProviderCallDiagnostic"]


class SDK:
    def __init__(self):
        self.kwargs = None
        self.entered = asyncio.Event()
        self.response_gate = asyncio.Event()
        self.chunk_gate = asyncio.Event()
        self.finish_gate = asyncio.Event()
        for gate in (self.response_gate, self.chunk_gate, self.finish_gate):
            gate.set()

    async def acompletion(self, **kwargs):
        self.kwargs = kwargs
        self.entered.set()
        await self.response_gate.wait()

        async def chunks():
            await self.chunk_gate.wait()
            for text in (None, "ok"):
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
                )
            await self.finish_gate.wait()

        return chunks()


def setup(monkeypatch, recorder):
    sdk = SDK()
    monkeypatch.setattr("fusion_cli.providers.litellm_provider._litellm", lambda: sdk)
    monkeypatch.setattr(
        LiteLlmProvider,
        "_rebuild",
        lambda self, chunks, req, started: ModelResult("r", "test/model", "ok", 0, True),
    )
    leaf = LiteLlmProvider("test/model", role="r")
    wrapped = EventingProvider(
        leaf,
        publisher=recorder,
        role="r",
        channel=Channel.SUBAGENT,
        purpose="actor",
        call_id_factory=lambda: "call-1",
    )
    return sdk, leaf, wrapped


async def consume(provider, req):
    return [item async for item in provider.stream(req)]


async def test_leaf_phases_include_empty_sdk_chunks(monkeypatch):
    recorder = Recorder()
    sdk, leaf, wrapped = setup(monkeypatch, recorder)
    req = replace(request(), conversation_id="synthetic-session")
    result = await consume(wrapped, req)
    assert [event.phase for event in diagnostics(recorder)] == [
        "call_enter",
        "leaf_enter",
        "sdk_await_enter",
        "sdk_stream_open",
        "sdk_first_chunk",
        "call_end",
    ]
    snapshot = diagnostics(recorder)[-1]
    assert (
        snapshot.leaf_attempts,
        snapshot.sdk_chunks,
        snapshot.sdk_text_chunks,
        snapshot.sdk_empty_text_chunks,
    ) == (1, 2, 1, 1)
    assert {event.call_id for event in diagnostics(recorder)} == {"call-1"}
    assert result[-1].result.text == "ok"
    assert sdk.kwargs == leaf._call_kwargs(req, stream=True)


async def wait_phase(recorder, phase):
    async with asyncio.timeout(2):
        while not any(event.phase == phase for event in diagnostics(recorder)):
            recorder.changed.clear()
            await recorder.changed.wait()


async def test_gated_sdk_open_and_chunk_wait_are_distinct(monkeypatch):
    recorder = Recorder()
    sdk, _leaf, wrapped = setup(monkeypatch, recorder)
    sdk.response_gate.clear()
    sdk.chunk_gate.clear()
    task = asyncio.create_task(consume(wrapped, request()))
    try:
        await sdk.entered.wait()
        assert diagnostics(recorder)[-1].phase == "sdk_await_enter"
        sdk.response_gate.set()
        await wait_phase(recorder, "sdk_stream_open")
        assert not any(event.phase == "sdk_first_chunk" for event in diagnostics(recorder))
        sdk.chunk_gate.set()
        await task
        assert diagnostics(recorder)[-1].sdk_chunks == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize(
    "gate,phase,count",
    [
        ("response_gate", "sdk_await_enter", 0),
        ("chunk_gate", "sdk_stream_open", 0),
        ("finish_gate", "sdk_first_chunk", 2),
    ],
)
async def test_cancel_preserves_last_phase_and_aggregate(monkeypatch, gate, phase, count):
    recorder = Recorder()
    sdk, _leaf, wrapped = setup(monkeypatch, recorder)
    getattr(sdk, gate).clear()
    task = asyncio.create_task(consume(wrapped, request()))
    await wait_phase(recorder, phase)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    terminal = diagnostics(recorder)[-1]
    assert terminal.phase == "call_cancelled"
    assert terminal.previous_phase == phase
    assert terminal.sdk_chunks == count
    assert sum(type(e).__name__ == "ModelCallAbandoned" for e in recorder.events) == 1
    assert not any(type(e).__name__ == "ModelCallFinished" for e in recorder.events)
    assert sum(e.phase == "call_cancelled" for e in diagnostics(recorder)) == 1


class GateSleeper:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def sleep(self, seconds):
        self.entered.set()
        await self.release.wait()


class Ledger:
    def __init__(self):
        self.calls = 0

    def cooled_until(self, key):
        return 0

    def take_token(self, key, rate):
        self.calls += 1
        return 1.0 if self.calls == 1 else 0.0


@pytest.mark.parametrize("cancel", [False, True])
async def test_rate_wait_has_no_leaf_until_admission(monkeypatch, cancel):
    from fusion_cli.providers.rate_gate import RateGatedProvider

    recorder = Recorder()
    _sdk, leaf, _wrapped = setup(monkeypatch, recorder)
    sleeper = GateSleeper()
    gate = RateGatedProvider(
        leaf,
        ledger=Ledger(),
        key="secret-key-hash",
        per_minute=40,
        pace_max_wait_s=2,
        cooldown_s=60,
        sleeper=sleeper,
    )
    wrapped = EventingProvider(gate, publisher=recorder, role="r", channel=Channel.SUBAGENT)
    task = asyncio.create_task(consume(wrapped, request()))
    await sleeper.entered.wait()
    assert diagnostics(recorder)[-1].phase == "rate_wait"
    assert diagnostics(recorder)[-1].wait_ms == 1000
    assert not any(e.phase == "leaf_enter" for e in diagnostics(recorder))
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert diagnostics(recorder)[-1].previous_phase == "rate_wait"
        assert diagnostics(recorder)[-1].leaf_attempts == 0
    else:
        sleeper.release.set()
        await task
        phases = [e.phase for e in diagnostics(recorder)]
        assert (
            phases.index("rate_wait_end")
            < phases.index("rate_admitted")
            < phases.index("leaf_enter")
        )


async def test_retry_wait_counts_real_leaf_invocations(monkeypatch):
    from fusion_cli.providers.retrying import RetryingProvider

    recorder = Recorder()
    sdk, leaf, _wrapped = setup(monkeypatch, recorder)
    original = sdk.acompletion
    calls = 0

    async def fail_once(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic private provider error")
        return await original(**kwargs)

    sdk.acompletion = fail_once
    sleeper = GateSleeper()
    retry = RetryingProvider(leaf, delays_s=(0.5,), sleeper=sleeper)
    wrapped = EventingProvider(retry, publisher=recorder, role="r", channel=Channel.SUBAGENT)
    task = asyncio.create_task(consume(wrapped, request()))
    await sleeper.entered.wait()
    assert diagnostics(recorder)[-1].phase == "provider_retry_wait"
    assert diagnostics(recorder)[-1].leaf_attempts == 1
    sleeper.release.set()
    await task
    assert diagnostics(recorder)[-1].leaf_attempts == 2
    assert diagnostics(recorder)[-1].sdk_chunks == 2


@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_broken_diagnostic_callback_cannot_change_result(monkeypatch, error):
    class BrokenRecorder(Recorder):
        def publish(self, event):
            if type(event).__name__ == "ProviderCallDiagnostic":
                raise error("synthetic diagnostic failure")
            super().publish(event)

    recorder = BrokenRecorder()
    _sdk, leaf, wrapped = setup(monkeypatch, recorder)
    observed = await consume(wrapped, request())
    plain = await consume(leaf, request())
    assert observed == plain
    assert sum(type(e).__name__ == "ModelCallFinished" for e in recorder.events) == 1


async def test_diagnostic_is_trace_only_and_replayable_with_correlation(monkeypatch):
    import io
    import json

    from fusion_cli.appserver.bridges import ProtocolSink
    from fusion_cli.observability.bus import EventBus
    from fusion_cli.observability.json_sink import JsonRenderer
    from fusion_cli.observability.replay import event_from_payload

    recorder = Recorder()
    _sdk, _leaf, wrapped = setup(monkeypatch, recorder)
    secret = "sentinel-private-prompt-reasoning-key-header-url"
    req = replace(request(), messages=(replace(request().messages[0], content=secret),))
    await consume(wrapped, req)
    trace = io.StringIO()
    protocol = []

    def correlate(event):
        return replace(event, session_id="session", turn_id="attempt", event_id="e")

    async with EventBus(event_correlator=correlate) as bus:
        bus.subscribe(JsonRenderer(trace))
        bus.subscribe(ProtocolSink(protocol.append))
        for event in recorder.events:
            bus.publish(event)
    payloads = [json.loads(line) for line in trace.getvalue().splitlines()]
    diag = [p for p in payloads if p["event"] == "ProviderCallDiagnostic"]
    assert diag
    assert all(p["session_id"] == "session" and p["turn_id"] == "attempt" for p in diag)
    assert all(p["call_id"] == "call-1" for p in diag)
    assert secret not in json.dumps(diag)
    assert "secret-key-hash" not in json.dumps(diag)
    assert all("ProviderCallDiagnostic" not in line for line in protocol)
    assert any("ModelCallStarted" in line for line in protocol)
    assert all(event_from_payload(p) is not None for p in diag)
    assert event_from_payload({"event": "UnknownFutureDiagnostic"}) is None
    allowed = {
        "event",
        "event_id",
        "session_id",
        "turn_id",
        "schema_version",
        "candidate_id",
        "agent_id",
        "call_id",
        "phase",
        "previous_phase",
        "elapsed_ms",
        "leaf_attempts",
        "sdk_chunks",
        "sdk_text_chunks",
        "sdk_empty_text_chunks",
        "max_tokens",
        "timeout_s",
        "requested_sdk_retries",
        "stream",
        "purpose",
        "background",
        "wait_ms",
    }
    assert all(set(p) <= allowed for p in diag)
    assert all(
        value is None or isinstance(value, (int, float, str, bool))
        for p in diag
        for value in p.values()
    )


def test_counter_bounds_terminal_once_and_clock_failure(monkeypatch):
    from fusion_cli.core.provider_diagnostics import ProviderCallObserver

    monkeypatch.setattr("fusion_cli.core.provider_diagnostics._COUNTER_MAX", 2)
    events = []
    observer = ProviderCallObserver(
        events.append,
        call_id="c",
        max_tokens=16,
        timeout_s=5,
        requested_sdk_retries=0,
        stream=True,
        purpose="actor",
        background=False,
        clock=lambda: 1.0,
    )
    for _ in range(5):
        observer.leaf_enter()
        observer.sdk_chunk(has_text=True)
        observer.sdk_chunk(has_text=False)
    observer.phase("call_end")
    observer.phase("call_cancelled")
    assert sum(e.phase == "call_end" for e in events) == 1
    assert not any(e.phase == "call_cancelled" for e in events)
    assert (
        events[-1].leaf_attempts,
        events[-1].sdk_chunks,
        events[-1].sdk_text_chunks,
        events[-1].sdk_empty_text_chunks,
    ) == (2, 2, 2, 2)

    def broken_clock():
        raise RuntimeError("clock detail must stay private")

    observer = ProviderCallObserver(
        events.append,
        call_id="c2",
        max_tokens=16,
        timeout_s=5,
        requested_sdk_retries=0,
        stream=True,
        purpose="actor",
        background=False,
        clock=broken_clock,
    )
    count = len(events)
    observer.phase("call_enter")
    observer.phase("call_end")
    assert len(events) == count


async def test_simultaneous_calls_keep_counters_and_context_separate(monkeypatch):
    from fusion_cli.core.web_provenance import WebCallContext

    recorder = Recorder()
    sdk, leaf, _wrapped = setup(monkeypatch, recorder)
    ids = iter(("one", "two"))
    wrapped = EventingProvider(
        leaf,
        publisher=recorder,
        role="r",
        channel=Channel.SUBAGENT,
        call_id_factory=lambda: next(ids),
    )
    sdk.finish_gate.clear()
    req = replace(request(), web_call_context=WebCallContext("s", "t", "t", ""))
    tasks = [asyncio.create_task(consume(wrapped, req)) for _ in range(2)]
    try:
        async with asyncio.timeout(2):
            while sum(e.phase == "sdk_first_chunk" for e in diagnostics(recorder)) < 2:
                recorder.changed.clear()
                await recorder.changed.wait()
        sdk.finish_gate.set()
        await asyncio.gather(*tasks)
        for identity in ("one", "two"):
            end = [e for e in diagnostics(recorder) if e.call_id == identity][-1]
            assert end.phase == "call_end"
            assert (end.leaf_attempts, end.sdk_chunks) == (1, 2)
        assert req.provider_observer is None
        assert req.web_call_context.model_call_id == ""
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_explicit_generator_close_records_one_cancellation(monkeypatch):
    recorder = Recorder()
    _sdk, _leaf, wrapped = setup(monkeypatch, recorder)
    stream = wrapped.stream(request())
    first = await anext(stream)
    assert first.provisional is True
    await stream.aclose()
    terminal = diagnostics(recorder)[-1]
    assert terminal.phase == "call_cancelled"
    assert terminal.sdk_chunks == 1
    assert terminal.sdk_empty_text_chunks == 1
    assert sum(type(e).__name__ == "ModelCallAbandoned" for e in recorder.events) == 1
    assert not any(type(e).__name__ == "ModelCallFinished" for e in recorder.events)


async def test_diagnostic_failure_does_not_swallow_provider_cancellation(monkeypatch):
    class BrokenRecorder(Recorder):
        def publish(self, event):
            if type(event).__name__ == "ProviderCallDiagnostic":
                raise RuntimeError("synthetic diagnostic failure")
            super().publish(event)

    recorder = BrokenRecorder()
    sdk, _leaf, wrapped = setup(monkeypatch, recorder)
    sdk.response_gate.clear()
    task = asyncio.create_task(consume(wrapped, request()))
    await sdk.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sum(type(e).__name__ == "ModelCallAbandoned" for e in recorder.events) == 1
    assert not any(type(e).__name__ == "ModelCallFinished" for e in recorder.events)

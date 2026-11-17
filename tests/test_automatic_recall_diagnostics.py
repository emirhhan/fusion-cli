from __future__ import annotations

import io
import json
from dataclasses import replace

from fusion_cli.appserver.bridges import ProtocolSink
from fusion_cli.observability.trace_store import TraceWriter
from tests.test_automatic_recall import Memory, enabled, hints


def diagnostics(deps):
    return [e for e in deps.publisher.events if type(e).__name__ == "AutomaticRecallDiagnostic"]


async def test_terminal_diagnostic_trace_only_and_no_content(tmp_path):
    deps = enabled(tmp_path, Memory("secret-lesson-content"))
    assert await hints(deps)
    (event,) = diagnostics(deps)
    assert event.status == "offered"
    assert event.source_version == "auto_recall_diag_v1"
    assert event.returned_count == event.formatted_count == 1
    trace, protocol = io.StringIO(), []
    TraceWriter(trace).handle(event)
    ProtocolSink(protocol.append).handle(event)
    assert protocol == []
    payload = json.loads(trace.getvalue())
    assert payload["event"] == "AutomaticRecallDiagnostic"
    assert "secret-lesson-content" not in trace.getvalue()
    assert set(payload) <= {
        "event",
        "candidate_id",
        "agent_id",
        "event_id",
        "session_id",
        "turn_id",
        "schema_version",
        "source_version",
        "memory_kind",
        "status",
        "phase",
        "elapsed_ms",
        "backend_operation",
        "backend_status",
        "error_class",
        "count_result",
        "returned_count",
        "formatted_count",
    }


async def test_diagnostic_disabled_no_memory_empty_rejected_and_failure(tmp_path):
    for memory, expected in [(None, "no_memory"), (Memory("X" * 100000), "rejected_format")]:
        deps = enabled(tmp_path, memory)
        assert not await hints(deps)
        assert diagnostics(deps)[0].status == expected
    deps = enabled(tmp_path, Memory())
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, lessons=False))
    assert not await hints(deps)
    assert diagnostics(deps)[0].status == "disabled_lessons"

    class Broken(Memory):
        def recall(self, *args, **kwargs):
            raise ValueError("private-error-message")

    deps = enabled(tmp_path, Broken())
    assert not await hints(deps)
    (event,) = diagnostics(deps)
    assert event.status == "error" and event.error_class == "ValueError"
    assert "private-error-message" not in repr(event)


async def test_diagnostic_sink_failure_does_not_change_hint(tmp_path):
    deps = enabled(tmp_path, Memory())
    publish = deps.publisher.publish

    def fail(event):
        if type(event).__name__ == "AutomaticRecallDiagnostic":
            raise RuntimeError("private sink error")
        publish(event)

    deps.publisher.publish = fail
    assert await hints(deps)
    assert len(deps.recalled_lessons) == 1


async def test_actual_eventbus_tracewriter_native_projection(tmp_path):
    from fusion_cli.observability.bus import EventBus
    from fusion_cli.observability.replay import event_from_payload

    deps = enabled(tmp_path, Memory())
    trace, protocol = io.StringIO(), []

    def correlate(event):
        return replace(
            event, session_id="session", turn_id="attempt", event_id="e", schema_version=1
        )

    async with EventBus(event_correlator=correlate) as bus:
        bus.subscribe(TraceWriter(trace))
        bus.subscribe(ProtocolSink(protocol.append))
        deps.publisher = bus
        assert await hints(deps)
    payloads = [json.loads(line) for line in trace.getvalue().splitlines()]
    (event,) = [p for p in payloads if p["event"] == "AutomaticRecallDiagnostic"]
    assert event["session_id"] == "session" and event["turn_id"] == "attempt"
    assert event_from_payload(event).status == "offered"
    assert all("AutomaticRecallDiagnostic" not in line for line in protocol)
    assert any("LessonsRecalled" in line for line in protocol)


async def test_backend_count_query_error_lock_and_cooldown(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from fusion_cli.memory import store

    class Native:
        name = "private-collection-name"

        def __init__(self):
            self.calls = []

        def count(self):
            self.calls.append("count")
            return 61

        def query(self):
            self.calls.append("query")
            raise ValueError("private-backend-message")

    native = Native()

    class GuardedMemory(Memory):
        def recall(self, *args, **kwargs):
            guarded = store.GuardedCollection(native, tmp_path)
            if not guarded.count():
                return ()
            guarded.query()
            return ()

    deps = enabled(tmp_path, GuardedMemory())
    assert not await hints(deps)
    (event,) = diagnostics(deps)
    assert event.status == "error"
    assert event.backend_operation == "query" and event.backend_status == "error"
    assert event.count_result == 61 and event.error_class == "ValueError"
    assert native.calls == ["count", "query"]
    assert "private-" not in repr(event)

    store._disabled[(tmp_path, native.name)] = float("inf")
    try:
        deps = enabled(tmp_path, GuardedMemory())
        assert not await hints(deps)
        (event,) = diagnostics(deps)
        assert event.status == event.backend_status == "cooldown"
        assert event.backend_operation == "count" and event.count_result is None
        assert native.calls == ["count", "query"]
    finally:
        store._disabled.pop((tmp_path, native.name))

    @contextmanager
    def unavailable(*args):
        yield False

    monkeypatch.setattr(store, "process_lock", unavailable)
    deps = enabled(tmp_path, GuardedMemory())
    assert not await hints(deps)
    (event,) = diagnostics(deps)
    assert event.status == event.backend_status == "lock_unavailable"
    assert event.backend_operation == "count"
    assert native.calls == ["count", "query"]


async def test_timeout_busy_cancel_stale_owner_and_no_late_diagnostic(tmp_path, monkeypatch):
    import asyncio

    from fusion_cli.engines.agent import automatic_recall
    from tests.test_automatic_recall import BlockingMemory, release_worker, wait_for_event

    monkeypatch.setattr(automatic_recall, "AUTO_RECALL_TIMEOUT_S", 0.03)
    for cancel in (False, True):
        memory = BlockingMemory()
        deps = enabled(tmp_path, memory)
        task = asyncio.create_task(hints(deps))
        try:
            await wait_for_event(memory.entered)
            if cancel:
                task.cancel()
                import pytest

                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                assert not await task
            (event,) = diagnostics(deps)
            assert event.status == ("cancelled" if cancel else "timeout")
            assert event.phase == "recall"
            other = enabled(tmp_path, Memory())
            assert not await hints(other)
            assert diagnostics(other)[0].status == "busy"
            assert not other.lessons.calls
        finally:
            await release_worker(memory)
        assert len(diagnostics(deps)) == 1
        assert not deps.recalled_lessons

    monkeypatch.setattr(automatic_recall, "AUTO_RECALL_TIMEOUT_S", 1)
    memory = BlockingMemory()
    deps = enabled(tmp_path, memory)
    task = asyncio.create_task(hints(deps))
    try:
        await wait_for_event(memory.entered)
        deps.attempt_id = "other-owner"
    finally:
        await release_worker(memory)
    assert not await task
    assert diagnostics(deps)[0].status == "stale_owner"
    assert not deps.recalled_lessons


async def test_empty_exhausted_and_diagnostic_collector_failure(tmp_path, monkeypatch):
    from fusion_cli.core.turn_deadline import TurnDeadline
    from fusion_cli.memory import store
    from fusion_cli.memory.null import NullLessonMemory

    deps = enabled(tmp_path, NullLessonMemory())
    assert not await hints(deps)
    assert diagnostics(deps)[0].status == "empty"
    deps = enabled(tmp_path, Memory())
    deps.deadline = TurnDeadline(deps.clock, deps.clock.monotonic() - 1)
    assert not await hints(deps)
    assert diagnostics(deps)[0].status == "exhausted_budget"
    assert not deps.lessons.calls

    def broken(*args, **kwargs):
        raise RuntimeError("private collector failure")

    monkeypatch.setattr(store._AutomaticReadDiagnostic, "note", broken)
    deps = enabled(tmp_path, Memory())
    assert await hints(deps)
    assert diagnostics(deps)[0].status == "offered"


async def test_count_error_is_distinct_from_genuine_zero_without_extra_queries(tmp_path):
    from fusion_cli.memory.store import GuardedCollection

    class Native:
        name = "private"

        def __init__(self, fail):
            self.fail = fail
            self.calls = []

        def count(self):
            self.calls.append("count")
            if self.fail:
                raise RuntimeError("private error")
            return 0

        def query(self):
            raise AssertionError("query must not run when count is zero")

    for fail in (False, True):
        native = Native(fail)

        class GuardedMemory(Memory):
            def __init__(self, backend):
                super().__init__()
                self.backend = backend

            def recall(self, *args, **kwargs):
                assert GuardedCollection(self.backend, tmp_path).count() == 0
                return ()

        deps = enabled(tmp_path, GuardedMemory(native))
        assert not await hints(deps)
        (event,) = diagnostics(deps)
        assert event.status == ("error" if fail else "empty")
        assert event.backend_operation == "count"
        assert event.backend_status == ("error" if fail else "ok")
        assert event.count_result == (None if fail else 0)
        assert native.calls == ["count"]


async def test_timeout_snapshots_inflight_backend_operation(tmp_path, monkeypatch):
    import asyncio
    import threading

    from fusion_cli.engines.agent import automatic_recall
    from fusion_cli.memory.store import GuardedCollection
    from tests.test_automatic_recall import wait_for_event

    monkeypatch.setattr(automatic_recall, "AUTO_RECALL_TIMEOUT_S", 0.03)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    class Native:
        name = "private"

        def count(self):
            return 61

        def query(self):
            entered.set()
            try:
                assert release.wait(5)
            finally:
                finished.set()

    class GuardedMemory(Memory):
        def recall(self, *args, **kwargs):
            guarded = GuardedCollection(Native(), tmp_path)
            guarded.count()
            guarded.query()
            return ()

    deps = enabled(tmp_path, GuardedMemory())
    try:
        task = asyncio.create_task(hints(deps))
        await wait_for_event(entered)
        assert not await task
        (event,) = diagnostics(deps)
        assert event.status == "timeout" and event.phase == "backend_call"
        assert event.backend_operation == "query" and event.backend_status == "running"
        assert event.count_result == 61
    finally:
        release.set()
        await wait_for_event(finished)
        await asyncio.sleep(0.01)
    assert len(diagnostics(deps)) == 1


async def test_memory_kind_uses_allowlisted_concrete_types_without_opening_backend(tmp_path):
    from fusion_cli.memory.lessons import ChromaLessonMemory
    from fusion_cli.memory.null import NullLessonMemory

    chroma = object.__new__(ChromaLessonMemory)

    class Other:
        pass

    for memory, kind in [
        (None, "none"),
        (NullLessonMemory(), "null"),
        (chroma, "chroma"),
        (Other(), "other"),
    ]:
        deps = enabled(tmp_path, memory)
        deps.config = replace(deps.config, runtime=replace(deps.config.runtime, lessons=False))
        assert not await hints(deps)
        assert diagnostics(deps)[0].memory_kind == kind


def test_safe_error_categories_do_not_expose_custom_class_names():
    from fusion_cli.memory.store import _diagnostic_error_class

    for cls in (ModuleNotFoundError, ImportError, AttributeError, TypeError):
        assert _diagnostic_error_class(cls("private error")) == cls.__name__
    private_type = type("private-secret-custom-class", (Exception,), {})
    assert _diagnostic_error_class(private_type("private")) == "OtherError"

"""Automatic hints must remain optional, bounded, and owned by the current attempt."""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from dataclasses import replace

import pytest

from fusion_cli.core.events import LessonOffered, LessonsRecalled
from fusion_cli.core.memory import Lesson, LessonKind
from fusion_cli.engines.agent import learning_steps, loop
from fusion_cli.memory.null import NullLessonMemory
from tests.fakes import ScriptedProvider, model_result
from tests.test_agent_lessons import _deps
from tests.test_ask_teacher import _Publisher


class Memory(NullLessonMemory):
    def __init__(self, text="ÖNCE DOSYAYI OKU", delay=0):
        self.lesson = Lesson(text, LessonKind.SUCCESS, id="lesson1")
        self.delay = delay
        self.calls = 0

    def recall(self, query, **kwargs):
        self.calls += 1
        time.sleep(self.delay)
        return (self.lesson,)


def enabled(tmp_path, memory):
    deps = _deps(tmp_path)
    deps.config = replace(
        deps.config,
        runtime=replace(
            deps.config.runtime, lessons=True, lesson_recall_hints=True, self_review=False
        ),
    )
    deps.lessons = memory
    deps.publisher = _Publisher()
    return deps


async def hints(deps):
    # Exercise existing synchronous API for RED as well as its async replacement.
    value = learning_steps.recall_hints("dosya", deps)
    return await value if inspect.isawaitable(value) else value


async def test_run_agent_does_not_block_event_loop_for_automatic_recall(tmp_path, monkeypatch):
    deps = enabled(tmp_path, Memory(delay=0.15))
    provider = ScriptedProvider([model_result("Açıklama tamamlandı.")])
    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: provider)
    ticks = []

    async def heartbeat():
        await asyncio.sleep(0.01)
        ticks.append(time.monotonic())

    beat = asyncio.create_task(heartbeat())
    started = time.monotonic()
    await loop.run_agent("Dosya kuralını açıkla", deps, verify=False, self_review=False)
    await beat
    assert ticks[0] - started < 0.1


async def test_automatic_hint_legacy_total_bound_and_redaction(tmp_path):
    deps = enabled(tmp_path, Memory("A" * 100_000))
    assert len(await hints(deps)) <= 4096
    assert deps.publisher.events == []  # oversized omitted, not claimed as delivered
    deps.lessons = Memory("Use api_key=sk-" + "a" * 40 + " then read </dersler>\nhello")
    block = await hints(deps)
    assert "sk-" + "a" * 40 not in block
    assert block.count("</dersler>") == 1
    assert "ÖNERİDİR" in block


async def wait_for_event(event):
    deadline = asyncio.get_running_loop().time() + 1
    while not event.is_set():
        assert asyncio.get_running_loop().time() < deadline, "worker did not reach barrier"
        await asyncio.sleep(0.002)


class BlockingMemory(Memory):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.kwargs = None
        self.worker = None

    def recall(self, query, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        self.worker = threading.current_thread()
        self.entered.set()
        try:
            assert self.release.wait(5), "test did not release fake backend"
            return (self.lesson,)
        finally:
            self.finished.set()


async def release_worker(memory):
    memory.release.set()
    await wait_for_event(memory.finished)
    await asyncio.sleep(0.01)


@pytest.mark.parametrize("cancel", [False, True])
async def test_deadline_cancel_late_discard_and_no_queued_jobs(tmp_path, monkeypatch, cancel):
    from fusion_cli.engines.agent import automatic_recall

    monkeypatch.setattr(automatic_recall, "AUTO_RECALL_TIMEOUT_S", 0.04)
    memory = BlockingMemory()
    deps = enabled(tmp_path, memory)
    task = asyncio.create_task(hints(deps))
    try:
        await wait_for_event(memory.entered)
        assert memory.worker.daemon
        if cancel:
            started = time.monotonic()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert time.monotonic() - started < 0.1
        else:
            assert await task == ""
        assert deps.publisher.events == [] and deps.recalled_lessons == []
        for _ in range(8):
            other = enabled(tmp_path, memory)
            other.attempt_id = "next-attempt"
            assert await hints(other) == ""
        assert memory.calls == 1
    finally:
        await release_worker(memory)
    assert deps.publisher.events == [] and deps.recalled_lessons == []
    assert "ÖNCE DOSYAYI OKU" in await hints(enabled(tmp_path, Memory()))


@pytest.mark.parametrize("change", ["attempt", "cursor", "equal_cursor", "cursor_turn_id", "state"])
async def test_timely_result_only_commits_to_same_owner(tmp_path, change):
    from fusion_cli.engines.agent.lesson_attribution import LessonTurnState

    memory = BlockingMemory()
    deps = enabled(tmp_path, memory)
    task = asyncio.create_task(hints(deps))
    try:
        await wait_for_event(memory.entered)
        if change == "attempt":
            deps.attempt_id = "other"
        elif change == "cursor":
            deps.original_cursor = object()  # identity changed before delivery
        elif change == "equal_cursor":
            original = deps.original_cursor
            deps.original_cursor = replace(original)
            assert deps.original_cursor == original and deps.original_cursor is not original
        elif change == "cursor_turn_id":
            deps.original_cursor.turn_id = "another-attempt"
        else:
            deps.lesson_state = LessonTurnState()
    finally:
        await release_worker(memory)
    assert await task == ""
    assert deps.recalled_lessons == [] and deps.publisher.events == []


async def test_scope_snapshot_is_immutable_and_filesystem_probes_are_off_loop(
    tmp_path, monkeypatch
):
    from fusion_cli.core.lesson_runtime import LessonRuntimeContext
    from fusion_cli.core.memory import LessonRecallPolicy
    from fusion_cli.engines.agent import verify_discovery

    memory = BlockingMemory()
    deps = enabled(tmp_path, memory)
    deps.lesson_owner = "reader"
    deps.lesson_context = LessonRuntimeContext(LessonRecallPolicy(source_split="development"))
    thread_ids = []

    def kinds(root):
        thread_ids.append(threading.get_ident())
        return ("python",)

    monkeypatch.setattr(verify_discovery, "project_kinds", kinds)
    task = asyncio.create_task(hints(deps))
    try:
        await wait_for_event(memory.entered)
        deps.lesson_owner = "other"
        deps.lesson_context = LessonRuntimeContext()
    finally:
        await release_worker(memory)
    assert await task
    assert thread_ids == [memory.worker.ident]
    assert thread_ids[0] != threading.get_ident()
    assert memory.kwargs["tags"] == ("ajan:reader", "python")
    assert memory.kwargs["policy"].source_split == "development"
    assert memory.kwargs["workspace"] == str(tmp_path.resolve())
    assert memory.kwargs["limit"] == 2
    assert sum(isinstance(e, LessonsRecalled) for e in deps.publisher.events) == 1
    assert sum(isinstance(e, LessonOffered) for e in deps.publisher.events) == 1


async def test_real_guarded_backend_has_no_nested_abandoned_worker(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import automatic_recall
    from fusion_cli.memory import store

    monkeypatch.setattr(automatic_recall, "AUTO_RECALL_TIMEOUT_S", 0.02)
    monkeypatch.setattr(store, "CALL_TIMEOUT_S", 0.01)

    class Native:
        name = "lesson-test"
        calls = 0
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        thread = None

        def count(self):
            return 1

        def query(self, **kw):
            self.calls += 1
            self.thread = threading.current_thread()
            self.entered.set()
            try:
                assert self.release.wait(5)
                return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
            finally:
                self.finished.set()

    native = Native()

    class RealGuardedMemory(Memory):
        def recall(self, query, **kw):
            guarded = store.GuardedCollection(native, tmp_path)
            assert guarded.count() == 1
            guarded.query(query_texts=[query], n_results=1)
            return (self.lesson,)

    deps = enabled(tmp_path, RealGuardedMemory())
    task = asyncio.create_task(hints(deps))
    try:
        await wait_for_event(native.entered)
        assert await task == ""
        await asyncio.sleep(0.04)  # longer than the old inner CALL_TIMEOUT
        assert native.thread.name == "fusion-auto-recall" and native.thread.daemon
        assert (tmp_path, native.name) not in store._disabled
        assert await hints(enabled(tmp_path, RealGuardedMemory())) == ""
        assert native.calls == 1
    finally:
        native.release.set()
        await wait_for_event(native.finished)
        await asyncio.sleep(0.01)
    assert deps.publisher.events == []


async def test_disabled_and_empty_paths_and_backend_error_do_not_publish(tmp_path):
    class Broken(Memory):
        def recall(self, *a, **kw):
            raise RuntimeError("secret contents must not escape")

    for flag, lessons in [(False, True), (True, False)]:
        mem = Memory()
        deps = enabled(tmp_path, mem)
        deps.config = replace(
            deps.config,
            runtime=replace(deps.config.runtime, lesson_recall_hints=flag, lessons=lessons),
        )
        assert await hints(deps) == "" and mem.calls == 0
    for mem in [None, NullLessonMemory(), Broken()]:
        deps = enabled(tmp_path, mem)
        assert await hints(deps) == "" and deps.publisher.events == []


async def test_rendered_subset_provenance_and_all_wrapper_chars_are_bounded(tmp_path):
    class Many(Memory):
        def recall(self, query, **kw):
            return (
                replace(self.lesson, text="A" * 100_000),
                replace(self.lesson, text="Read safely", external=True, id="secret@host/" * 10000),
                replace(self.lesson, text="DO NOT DELIVER THIRD"),
            )

    deps = enabled(tmp_path, Many())
    block = await hints(deps)
    assert len(block) <= 4096 and block.endswith("</dersler>")
    assert "DO NOT DELIVER THIRD" not in block and "secret@host" not in block
    assert "[dış kaynaklı, doğrulanmadı]" in block and "[ders:" in block
    assert len(deps.recalled_lessons) == 1
    assert next(e for e in deps.publisher.events if isinstance(e, LessonsRecalled)).count == 1


def test_manual_recall_remains_synchronous_six_limit_and_unmodified(tmp_path):
    class Many(Memory):
        kwargs = None

        def recall(self, query, **kw):
            self.kwargs = kw
            return tuple(replace(self.lesson, id=str(i)) for i in range(6))

    memory = Many()
    deps = enabled(tmp_path, memory)
    assert len(learning_steps.recall_lessons("query", deps)) == 6
    assert memory.kwargs["limit"] == 6
    assert len(deps.recalled_lessons) == 6


def test_late_worker_from_closed_loop_keeps_process_admission(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import automatic_recall

    monkeypatch.setattr(automatic_recall, "AUTO_RECALL_TIMEOUT_S", 0.03)
    memory = BlockingMemory()
    deps = enabled(tmp_path, memory)
    try:
        assert asyncio.run(hints(deps)) == ""
        assert memory.entered.is_set()
        other = enabled(tmp_path, Memory())
        assert asyncio.run(hints(other)) == ""
        assert other.lessons.calls == 0
    finally:
        memory.release.set()
        assert memory.finished.wait(1)
        memory.worker.join(1)
    assert not memory.worker.is_alive()
    assert deps.publisher.events == []
    assert asyncio.run(hints(enabled(tmp_path, Memory())))


def test_daemon_backend_does_not_hold_asyncio_run_or_cli_exit(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    source = """
import asyncio, threading
from pathlib import Path
from fusion_cli.engines.agent import automatic_recall as a
from fusion_cli.core.memory import LessonRecallPolicy
from fusion_cli.memory.null import NullLessonMemory
from fusion_cli.memory.store import GuardedCollection
class Native:
    name = "exit-test"
    def query(self):
        threading.Event().wait()  # deliberately NEVER released in this child process
native = Native()
def blocked(request):
    from fusion_cli.memory.store import _automatic_read_scope
    with _automatic_read_scope():
        GuardedCollection(native, Path(".")).query()
a._read = blocked
a.AUTO_RECALL_TIMEOUT_S = .03
request = a.RecallRequest(NullLessonMemory(), "x", Path("."), (), "", LessonRecallPolicy())
async def main():
    assert not (await a.retrieve(request)).block
asyncio.run(main())
print("EXIT_WITH_BUSY_DAEMON", flush=True)
"""
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=8,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
            "PRODUCTION": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "EXIT_WITH_BUSY_DAEMON" in result.stdout


async def test_actual_memory_policy_is_same_for_automatic_and_manual(tmp_path, monkeypatch):
    from fusion_cli.core.lesson_runtime import LessonRuntimeContext
    from fusion_cli.core.memory import LessonRecallPolicy
    from fusion_cli.memory import lessons
    from tests.test_agent_lessons import _Koleksiyon

    candidates = [
        Lesson("Allowed", LessonKind.SUCCESS, source_split="dev"),
        Lesson("Blind", LessonKind.SUCCESS, source_split="blind"),
        Lesson("Quarantined", LessonKind.SUCCESS, source_split="dev", quarantined=True),
        Lesson("Other agent", LessonKind.SUCCESS, source_split="dev", tags=("ajan:other",)),
    ]
    monkeypatch.setattr(lessons, "get_collection", lambda *a, **kw: _Koleksiyon(candidates))
    memory = lessons.ChromaLessonMemory(tmp_path)
    deps = enabled(tmp_path, memory)
    deps.lesson_context = LessonRuntimeContext(LessonRecallPolicy(source_split="dev"))
    manual = learning_steps.recall_lessons("query", deps)
    assert [lesson.text for lesson in manual] == ["Allowed"]
    deps.recalled_lessons.clear()
    deps.publisher.events.clear()
    block = await hints(deps)
    assert "Allowed" in block
    assert "Blind" not in block and "Quarantined" not in block and "Other agent" not in block
    assert [lesson.text for lesson in deps.recalled_lessons] == ["Allowed"]


@pytest.mark.parametrize("expired", [True, False])
async def test_automatic_hints_respect_existing_turn_deadline(tmp_path, expired):
    from fusion_cli.core.turn_deadline import TurnDeadline

    memory = BlockingMemory()
    deps = enabled(tmp_path, memory)
    deps.deadline = TurnDeadline.from_duration(0.02, deps.clock)
    if expired:
        await asyncio.sleep(0.03)
    started = time.monotonic()
    try:
        assert await hints(deps) == ""
        assert time.monotonic() - started < 0.1
        assert memory.calls == (0 if expired else 1)
        assert not deps.recalled_lessons and not deps.publisher.events
    finally:
        if memory.entered.is_set():
            await release_worker(memory)


@pytest.mark.parametrize("failure_at", [1, 2])
async def test_optional_publication_failure_rolls_back_attribution_and_actor_continues(
    tmp_path, monkeypatch, failure_at
):
    class FailingObserver(_Publisher):
        def publish(self, event):
            if isinstance(event, (LessonsRecalled, LessonOffered)):
                self.calls += 1
                if self.calls == failure_at:
                    raise RuntimeError("secret observer error")
            return super().publish(event)

    deps = enabled(tmp_path, Memory())
    deps.publisher = FailingObserver()
    deps.publisher.calls = 0
    provider = ScriptedProvider([model_result("Görev tamamlandı.")])
    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: provider)
    outcome = await loop.run_agent("Dosya kuralını açıkla", deps, verify=False, self_review=False)
    assert outcome.ok
    assert not deps.recalled_lessons and deps.lesson_state is None
    assert "ÖNCE DOSYAYI OKU" not in "\n".join(m.content for m in provider.seen_messages[0])


async def test_failed_optional_offer_preserves_existing_attribution(tmp_path):
    from fusion_cli.engines.agent.lesson_attribution import LessonTurnState

    class Broken(_Publisher):
        def publish(self, event):
            if isinstance(event, LessonOffered):
                raise RuntimeError("optional observer failed")
            super().publish(event)

    deps = enabled(tmp_path, Memory())
    old = Lesson("Existing", LessonKind.MISTAKE, id="existing")
    state = LessonTurnState(offered={"existing": old})
    deps.lesson_state = state
    deps.recalled_lessons.append(old)
    deps.publisher = Broken()
    assert await hints(deps) == ""
    assert deps.lesson_state is state
    assert state.offered == {"existing": old} and state.uses == {}
    assert deps.recalled_lessons == [old]

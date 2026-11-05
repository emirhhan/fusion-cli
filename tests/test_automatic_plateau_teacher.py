"""Automatic recovery needs a real stall and stays inside its advisory phase."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.core.events import StatusChanged, ToolExecuted, ToolOutcome
from fusion_cli.core.tools import Tool, ToolResult
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import loop
from fusion_cli.tools.registry import ToolRegistry
from tests.fakes import model_result, tool_call
from tests.test_teacher_first import _setup


def recovery_deps(monkeypatch, tmp_path, *, phase=0.02, request=600):
    deps, sink, *_ = _setup(monkeypatch, tmp_path)
    deps.config = replace(
        deps.config,
        runtime=replace(
            deps.config.runtime,
            teacher_auto_phase_timeout_s=phase,
            request_timeout_s=request,
        ),
    )
    return deps, sink


def registry_for(run):
    registry = ToolRegistry()
    registry.register(
        Tool(name="ask_teacher", description="Offline advisory stub", parameters={}, run=run)
    )
    return registry


async def test_recovery_times_out_at_automatic_cap_and_records_correlated_failure(
    monkeypatch, tmp_path
):
    deps, sink = recovery_deps(monkeypatch, tmp_path)
    cleaned = asyncio.Event()

    async def slow(_args, _context):
        try:
            await asyncio.sleep(1)
        finally:
            cleaned.set()
        return ToolResult("late advice")

    state = loop._State(model_calls_made=5, repeat_blocked=True)
    messages = [Message("user", "app.py hatasını düzelt")]
    await asyncio.wait_for(
        loop._consult_teacher_on_plateau(messages, deps, registry_for(slow), state),
        timeout=0.3,
    )

    assert cleaned.is_set()
    assert not state.teacher_advice_ok
    event = next(e for e in sink.events if isinstance(e, ToolExecuted))
    assert event.outcome is ToolOutcome.FAILED
    assert event.call_id == messages[-1].tool_call_id == messages[-2].tool_calls[0].id
    assert messages[-1].ok is False
    assert "late advice" not in messages[-1].content
    assert any(isinstance(e, StatusChanged) and "süre" in e.message for e in sink.events)


@pytest.mark.parametrize("remaining_source", ["deadline", "budget"])
async def test_recovery_reserves_main_work_from_authoritative_remaining_time(
    monkeypatch, tmp_path, remaining_source
):
    deps, _sink = recovery_deps(monkeypatch, tmp_path, phase=1)
    setattr(deps, remaining_source, SimpleNamespace(remaining_s=lambda: 0.04))
    cancelled = asyncio.Event()

    async def slow(_args, _context):
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.set()
        return ToolResult("late")

    state = loop._State()
    await asyncio.wait_for(
        loop._consult_teacher_on_plateau([], deps, registry_for(slow), state), timeout=0.3
    )
    assert cancelled.is_set()
    assert not state.teacher_advice_ok


async def test_expired_turn_does_not_start_automatic_recovery(monkeypatch, tmp_path):
    deps, _sink = recovery_deps(monkeypatch, tmp_path)
    deps.deadline = SimpleNamespace(remaining_s=lambda: 0)
    calls = []

    async def run(_args, _context):
        calls.append(True)
        return ToolResult("advice")

    state = loop._State()
    await loop._consult_teacher_on_plateau([], deps, registry_for(run), state)
    assert not calls
    assert not state.teacher_advice_ok


async def test_late_success_after_timeout_cannot_be_adopted(monkeypatch, tmp_path):
    deps, sink = recovery_deps(monkeypatch, tmp_path)
    cleaned = False

    async def swallowing(_args, _context):
        nonlocal cleaned
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            await asyncio.sleep(0.01)
            cleaned = True
            return ToolResult("late advice")

    state = loop._State()
    messages = []
    await loop._consult_teacher_on_plateau(messages, deps, registry_for(swallowing), state)
    assert cleaned
    assert not state.teacher_advice_ok
    assert messages[-1].ok is False
    assert not any(isinstance(e, ToolExecuted) and e.outcome is ToolOutcome.OK for e in sink.events)


@pytest.mark.parametrize("converted", [False, True])
async def test_user_cancellation_cannot_be_swallowed_or_reclassified(
    monkeypatch, tmp_path, converted
):
    deps, _sink = recovery_deps(monkeypatch, tmp_path, phase=1)
    started = asyncio.Event()
    cleaned = False

    async def swallowing(_args, _context):
        nonlocal cleaned
        started.set()
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError as error:
            cleaned = True
            if converted:
                raise TimeoutError from error
            return ToolResult("ignored cancellation")

    state = loop._State()
    task = asyncio.create_task(
        loop._consult_teacher_on_plateau([], deps, registry_for(swallowing), state)
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned
    assert not state.teacher_advice_ok


async def test_request_timeout_is_not_the_automatic_phase_budget(monkeypatch, tmp_path):
    deps, _sink = recovery_deps(monkeypatch, tmp_path, phase=0.2, request=0.001)

    async def run(_args, _context):
        await asyncio.sleep(0.02)
        return ToolResult("useful advice")

    state = loop._State()
    await loop._consult_teacher_on_plateau([], deps, registry_for(run), state)
    assert state.teacher_advice_ok


async def test_distinct_successful_reads_do_not_auto_consult_before_targeted_edit(
    monkeypatch, tmp_path
):
    path = tmp_path / "app.py"
    path.write_text("\n".join(f"value_{i} = {i}" for i in range(8)) + "\n")
    answers = [model_result(tool_calls=[tool_call("list_dir", path=".")])]
    answers.extend(
        model_result(tool_calls=[tool_call("read_file", path="app.py", offset=i, limit=2)])
        for i in (1, 3, 5, 7)
    )
    answers.extend(
        [
            model_result(
                tool_calls=[
                    tool_call("edit_file", path="app.py", old="value_0 = 0", new="value_0 = 1")
                ]
            ),
            model_result("app.py güncellendi."),
        ]
    )
    deps, _sink, teacher, _apprentice = _setup(monkeypatch, tmp_path, apprentice_answers=answers)

    async def no_automatic_plan(*_args, **_kwargs):
        return None

    monkeypatch.setattr(loop, "prepare_teacher_plan", no_automatic_plan)
    monkeypatch.setattr(loop, "review_teacher_changes", no_automatic_plan)
    result = await loop.run_agent(
        "app.py içindeki hatayı düzelt. Önce dosyayı oku; "
        "value_0 = 0 satırını value_0 = 1 olarak düzenle.",
        deps,
        self_review=False,
        verify=False,
    )

    assert result.ok, result.final_text
    assert "value_0 = 1" in path.read_text(), result.final_text
    assert teacher.calls == 0
    assert not deps.auto_teacher_used


def test_count_only_work_reminder_does_not_claim_a_stall(monkeypatch, tmp_path):
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    deps, _sink = recovery_deps(monkeypatch, tmp_path)
    state = loop._State(tool_calls_made=5)
    note = loop._exploration_note(
        state,
        ExecutionPolicy(is_web=False, complex_task=True),
        plan_mode=False,
        teacher_available=True,
    )
    assert note
    assert "ask_teacher" not in note
    assert loop._plateau_reason(state, deps, exploration_note=note) is None


@pytest.mark.parametrize("signal", ["repeat", "failure", "output", "stalled"])
def test_real_stall_signals_still_consult_with_or_without_a_plan(monkeypatch, tmp_path, signal):
    deps, _sink = recovery_deps(monkeypatch, tmp_path)
    state = loop._State()
    if signal == "repeat":
        state.repeat_blocked = True
    elif signal == "failure":
        state.repeated_failures[("read_file", "denied")] = 2
    elif signal == "output":
        state.same_output_counts[("read_file", "same")] = loop.SAME_OUTPUT_WARN_AT
    else:
        state.stalled = True
    assert loop._plateau_reason(state, deps, exploration_note=None)
    deps.pending_teacher_plan = object()
    assert loop._plateau_reason(state, deps, exploration_note=None)


def test_generic_recovery_question_does_not_invent_multiple_files(monkeypatch, tmp_path):
    deps, _sink = recovery_deps(monkeypatch, tmp_path)
    question = loop._plateau_question(deps, "tekrar koruması aynı okumayı engelledi")
    assert "çok dosyalı" not in question
    assert "tekrar koruması aynı okumayı engelledi" in question

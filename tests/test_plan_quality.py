"""Workflow quality correction must pass acceptance before completion."""

from unittest.mock import AsyncMock

import pytest

from fusion_cli.core.events import ExecutionCompleted
from fusion_cli.core.execution_plan import ExecutionPlan, PlanStatus
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import plan_runner
from fusion_cli.engines.agent.loop import AgentOutcome
from tests.test_plan_repair import _deps, _file_step


@pytest.mark.parametrize("break_file", [True, False])
async def test_quality_correction_rechecks_acceptance(monkeypatch, tmp_path, break_file):
    deps = _deps(tmp_path)
    plan = ExecutionPlan("quality", "original task", (_file_step("create", "a.txt"),))
    judge = AsyncMock(return_value="Improve the product behavior")
    monkeypatch.setattr(plan_runner.review, "review_turn", judge)
    calls = []

    async def agent(task, turn_deps, **kwargs):
        calls.append(kwargs)
        assert not any(isinstance(e, ExecutionCompleted) for e in deps.publisher.events)
        correction = len(calls) == 2
        if correction:
            assert kwargs["depth"] == 1
            assert kwargs["self_review"] is False
            assert kwargs["verify"] is False
            assert turn_deps.budget is deps.budget
            assert turn_deps.execution.max_model_calls == 11
            assert "original task" in task
        (tmp_path / "a.txt").write_text("bozuk" if correction and break_file else "sağlam")
        return AgentOutcome(
            final_text="corrected" if correction else "done",
            messages=[Message("assistant", "step trace")],
            model_calls_made=2 if correction else 1,
            tool_calls_made=1,
        )

    result = await plan_runner.run_execution_plan(
        "original task", deps, agent, plan=plan, self_review=True
    )
    assert result.ok is not break_file
    assert len(calls) == 2
    assert judge.await_count == 1
    assert judge.call_args.args[0] == "original task"
    assert Message("assistant", "step trace") in judge.call_args.args[2]
    assert result.model_calls_made == 4  # step + judge + correction
    assert result.tool_calls_made == 2
    assert result.final_verification_calls == 2
    saved = deps.checkpoint_store.load("quality")
    assert saved.plan.status is (PlanStatus.PAUSED if break_file else PlanStatus.COMPLETED)
    assert sum(isinstance(e, ExecutionCompleted) for e in deps.publisher.events) == int(
        not break_file
    )


@pytest.mark.parametrize("enabled,step_ok", [(False, True), (True, False)])
async def test_disabled_or_failed_workflow_skips_judge(monkeypatch, tmp_path, enabled, step_ok):
    deps = _deps(tmp_path, recovery=0)
    deps.config.runtime.self_review = enabled
    judge = AsyncMock(return_value="")
    monkeypatch.setattr(plan_runner.review, "review_turn", judge)
    plan = ExecutionPlan("quality", "task", (_file_step("create", "a.txt"),))

    async def agent(task, turn_deps, **kwargs):
        (tmp_path / "a.txt").write_text("sağlam")
        return AgentOutcome(final_text="done", messages=[], ok=step_ok)

    await plan_runner.run_execution_plan("task", deps, agent, plan=plan)
    judge.assert_not_awaited()


@pytest.mark.parametrize("explicit,final,expected_judge", [(False, 2, 0), (True, 1, 1)])
async def test_quality_override_and_exhausted_final_budget(
    monkeypatch, tmp_path, explicit, final, expected_judge
):
    deps = _deps(tmp_path, final=final)
    deps.config.runtime.self_review = True
    judge = AsyncMock(return_value="Make one necessary correction")
    monkeypatch.setattr(plan_runner.review, "review_turn", judge)
    plan = ExecutionPlan("quality", "task", (_file_step("create", "a.txt"),))
    calls = []

    async def agent(task, turn_deps, **kwargs):
        calls.append(task)
        (tmp_path / "a.txt").write_text("sağlam")
        return AgentOutcome(final_text="done", messages=[], model_calls_made=1)

    result = await plan_runner.run_execution_plan(
        "task", deps, agent, plan=plan, self_review=explicit
    )
    assert len(calls) == 1
    assert judge.await_count == expected_judge
    assert result.ok is (not explicit)
    if explicit:
        assert result.budget_stopped
        assert deps.checkpoint_store.load("quality").plan.status is PlanStatus.PAUSED


@pytest.mark.parametrize("failure", ["none", "agent", "cancel", "acceptance", "budget"])
async def test_quality_changes_follow_step_rollback_lifecycle(monkeypatch, tmp_path, failure):
    import asyncio

    deps = _deps(tmp_path)
    judge = AsyncMock(return_value="Create the missing supporting file")
    monkeypatch.setattr(plan_runner.review, "review_turn", judge)
    plan = ExecutionPlan("quality", "task", (_file_step("create", "a.txt"),))
    calls = 0
    original = tmp_path / "a.txt"
    added = tmp_path / "b.txt"

    async def agent(task, turn_deps, **kwargs):
        nonlocal calls
        calls += 1
        context = turn_deps.tool_context
        if calls == 1:
            original.write_text("sağlam")
            context.changes.record_created(original)
            context.touched.add(original)
        else:
            added.write_text("new supporting file")
            context.changes.record_created(added)
            context.touched.add(added)
            context.changes.record(original)
            original.write_text("bozuk" if failure == "acceptance" else "sağlam and improved")
            context.touched.add(original)
            if failure == "cancel":
                raise asyncio.CancelledError
        return AgentOutcome(
            final_text="done",
            messages=[],
            ok=not (calls == 2 and failure == "agent"),
            model_calls_made=12 if calls == 2 and failure == "budget" else 1,
        )

    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await plan_runner.run_execution_plan("task", deps, agent, plan=plan, self_review=True)
    else:
        result = await plan_runner.run_execution_plan(
            "task", deps, agent, plan=plan, self_review=True
        )
        assert result.ok is (failure == "none")
    if failure == "none":
        assert added in deps.tool_context.touched
        assert added in deps.tool_context.changes.paths
        deps.tool_context.changes.restore()
        assert not added.exists()
        assert not original.exists()
    else:
        assert not added.exists()
        assert added not in deps.tool_context.touched
        assert added not in deps.tool_context.changes.paths
        assert original.read_text() == "sağlam"
        assert not any(isinstance(e, ExecutionCompleted) for e in deps.publisher.events)


@pytest.mark.parametrize("resumed_ok", [False, True])
async def test_pending_quality_resumes_with_feedback_and_remaining_budget(
    monkeypatch, tmp_path, resumed_ok
):
    deps = _deps(tmp_path, final=4)
    feedback = "Fix the incomplete product behavior before finishing"
    judge = AsyncMock(return_value=feedback)
    monkeypatch.setattr(plan_runner.review, "review_turn", judge)
    plan = ExecutionPlan("quality", "task", (_file_step("create", "a.txt"),))
    calls = []

    async def agent(task, turn_deps, **kwargs):
        calls.append(task)
        if len(calls) == 1:
            (tmp_path / "a.txt").write_text("sağlam")
        else:
            assert feedback in task
            assert turn_deps.execution.max_model_calls == (11 if len(calls) == 2 else 9)
        return AgentOutcome(
            final_text="done",
            messages=[],
            model_calls_made=2,
            ok=len(calls) == 1 or (len(calls) == 3 and resumed_ok),
        )

    first = await plan_runner.run_execution_plan("task", deps, agent, plan=plan, self_review=True)
    assert not first.ok
    saved = deps.checkpoint_store.load("quality")
    assert saved.quality_feedback == feedback
    assert all(step.status.value == "completed" for step in saved.plan.steps)
    # Disabling new reviews cannot erase an unresolved saved finding.
    resumed = await plan_runner.run_execution_plan("continue", deps, agent, self_review=False)
    assert resumed.ok is resumed_ok
    assert len(calls) == 3
    judge.assert_awaited_once()
    saved = deps.checkpoint_store.load("quality")
    assert saved.quality_feedback == ("" if resumed_ok else feedback)
    usage = next(item for item in saved.budget_usage if item.scope == "$quality-review")
    assert usage.calls == 5  # one judge and two actual two-call corrections
    assert saved.plan.status is (PlanStatus.COMPLETED if resumed_ok else PlanStatus.PAUSED)


async def test_pending_quality_cannot_reset_exhausted_recovery(monkeypatch, tmp_path):
    deps = _deps(tmp_path, recovery=3, final=4)
    judge = AsyncMock(return_value="Fix the still incomplete behavior")
    monkeypatch.setattr(plan_runner.review, "review_turn", judge)
    plan = ExecutionPlan("quality", "task", (_file_step("create", "a.txt"),))
    calls = 0

    async def agent(task, turn_deps, **kwargs):
        nonlocal calls
        calls += 1
        (tmp_path / "a.txt").write_text("sağlam")
        return AgentOutcome(final_text="done", messages=[], model_calls_made=2, ok=calls == 1)

    assert not (
        await plan_runner.run_execution_plan("task", deps, agent, plan=plan, self_review=True)
    ).ok
    for _ in range(2):
        resumed = await plan_runner.run_execution_plan("continue", deps, agent, self_review=False)
        assert not resumed.ok
        assert resumed.budget_stopped
    assert calls == 2
    judge.assert_awaited_once()
    saved = deps.checkpoint_store.load("quality")
    assert saved.quality_feedback == "Fix the still incomplete behavior"
    assert saved.plan.status is PlanStatus.PAUSED
    assert next(item.calls for item in saved.budget_usage if item.scope == "$quality-review") == 3


@pytest.mark.parametrize("failure", ["cancel", "error"])
async def test_acceptance_interruption_preserves_quality_budget(monkeypatch, tmp_path, failure):
    import asyncio

    deps = _deps(tmp_path, recovery=3, final=3)
    judge = AsyncMock(return_value="Add the required supporting file")
    monkeypatch.setattr(plan_runner.review, "review_turn", judge)
    plan = ExecutionPlan("quality", "task", (_file_step("create", "a.txt"),))
    actual_acceptance = plan_runner.verify_plan_acceptance
    acceptance_calls = 0
    agent_calls = 0
    added = tmp_path / "b.txt"

    async def acceptance(*args, **kwargs):
        nonlocal acceptance_calls
        acceptance_calls += 1
        if acceptance_calls == 2:
            if failure == "cancel":
                raise asyncio.CancelledError
            raise RuntimeError("acceptance interrupted")
        return await actual_acceptance(*args, **kwargs)

    monkeypatch.setattr(plan_runner, "verify_plan_acceptance", acceptance)

    async def agent(task, turn_deps, **kwargs):
        nonlocal agent_calls
        agent_calls += 1
        if agent_calls == 1:
            (tmp_path / "a.txt").write_text("sağlam")
        else:
            added.write_text("supporting file")
            turn_deps.tool_context.changes.record_created(added)
            turn_deps.tool_context.touched.add(added)
        return AgentOutcome(final_text="done", messages=[], model_calls_made=2)

    with pytest.raises(asyncio.CancelledError if failure == "cancel" else RuntimeError):
        await plan_runner.run_execution_plan("task", deps, agent, plan=plan, self_review=True)
    assert not added.exists()
    saved = deps.checkpoint_store.load("quality")
    assert saved.quality_feedback == "Add the required supporting file"
    assert next(item.calls for item in saved.budget_usage if item.scope == "$quality-review") == 3
    assert (
        next(item.calls for item in saved.budget_usage if item.envelope == "final_verification")
        == 2
    )
    resumed = await plan_runner.run_execution_plan("continue", deps, agent, self_review=False)
    assert not resumed.ok
    assert resumed.budget_stopped
    assert agent_calls == 2
    assert acceptance_calls == 2
    judge.assert_awaited_once()

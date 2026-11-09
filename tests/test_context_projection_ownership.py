"""Optional context cannot revive another task or hold a turn behind disk I/O."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import replace

import pytest

from fusion_cli.core.checkpoint import WorkflowCheckpoint
from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
from fusion_cli.engines.agent import context_projection as projection

from .fakes import RecordingSink
from .test_agent_loop import _deps


def _checkpoint(tmp_path):
    step = PlanStep("old-step", "old task", (), (), (), ("OLD-CRITERION",), "", RetrySafety.SAFE)
    return WorkflowCheckpoint(
        ExecutionPlan("old-plan", "old task", (step,)), str(tmp_path), "chat", (), 1
    )


async def test_unbound_new_task_does_not_read_old_checkpoint(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    deps.conversation_id = "chat"

    class Store:
        def load(self, _plan_id):
            return _checkpoint(tmp_path)

    deps.checkpoint_store = Store()
    result = await projection.derive_context(deps)
    assert not result.note
    assert not result.pinned_call_ids


@pytest.mark.parametrize("mismatch", ["plan", "root", "chat"])
async def test_bound_context_rejects_wrong_checkpoint_owner(tmp_path, mismatch):
    deps = _deps(tmp_path, RecordingSink())
    deps.conversation_id = "chat"
    deps.context_plan_id = "old-plan"
    checkpoint = _checkpoint(tmp_path)
    if mismatch == "plan":
        checkpoint = replace(checkpoint, plan=replace(checkpoint.plan, plan_id="other"))
    elif mismatch == "root":
        checkpoint = replace(checkpoint, root=str(tmp_path / "other"))
    else:
        checkpoint = replace(checkpoint, conversation_id="other")

    class Store:
        def load(self, _plan_id):
            return checkpoint

    deps.checkpoint_store = Store()
    assert not (await projection.derive_context(deps)).note


async def test_optional_context_timeout_has_one_worker_and_discards_late_result(
    tmp_path, monkeypatch
):
    deps = _deps(tmp_path, RecordingSink())
    deps.conversation_id = "chat"
    deps.context_plan_id = "old-plan"
    release = threading.Event()
    calls = []
    monkeypatch.setattr(projection, "CONTEXT_TIMEOUT_S", 0.02, raising=False)

    class Store:
        def load(self, _plan_id):
            calls.append(1)
            release.wait(2)
            return _checkpoint(tmp_path)

    deps.checkpoint_store = Store()
    try:
        result = await asyncio.wait_for(projection.derive_context(deps), timeout=0.2)
        assert not result.note
        assert not (await asyncio.wait_for(projection.derive_context(deps), timeout=0.2)).note
        assert calls == [1]
    finally:
        release.set()
    await asyncio.sleep(0.03)
    assert not deps.active_context.note


async def test_optional_context_store_error_cannot_fail_main_task(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    deps.conversation_id = "chat"
    deps.context_plan_id = "old-plan"

    class Store:
        def load(self, _plan_id):
            raise OSError("PRIVATE-DETAIL")

    deps.checkpoint_store = Store()
    assert not (await projection.derive_context(deps)).note


async def test_accepted_plan_restores_criteria_and_current_step_supersedes_disk(tmp_path):
    from fusion_cli.core.execution_plan import StepStatus

    deps = _deps(tmp_path, RecordingSink())
    deps.conversation_id = "chat"
    deps.context_plan_id = "old-plan"
    checkpoint = _checkpoint(tmp_path)

    class Store:
        def load(self, _plan_id):
            return checkpoint

    deps.checkpoint_store = Store()
    assert "OLD-CRITERION" in (await projection.derive_context(deps)).note
    deps.context_step = replace(checkpoint.plan.steps[0], status=StepStatus.COMPLETED)
    assert not (await projection.derive_context(deps)).note


async def test_bound_plan_is_loaded_by_id_instead_of_latest_chat_checkpoint(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    deps.conversation_id = "chat"
    deps.context_plan_id = "old-plan"
    requested = []

    class Store:
        def load(self, plan_id):
            requested.append(plan_id)
            return _checkpoint(tmp_path)

        def find_resumable(self, *_args):
            return replace(_checkpoint(tmp_path), plan=ExecutionPlan("unrelated", "new task", ()))

    deps.checkpoint_store = Store()
    assert "OLD-CRITERION" in (await projection.derive_context(deps)).note
    assert requested == ["old-plan"]


async def test_cancelled_context_read_never_occupies_default_executor(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    deps.conversation_id = "chat"
    deps.context_plan_id = "old-plan"
    started = threading.Event()
    release = threading.Event()

    class Store:
        def load(self, _plan_id):
            started.set()
            release.wait(2)
            return _checkpoint(tmp_path)

    deps.checkpoint_store = Store()
    task = asyncio.create_task(projection.derive_context(deps))
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.001)
        assert started.is_set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.2)
        assert not (await projection.derive_context(deps)).note
    finally:
        release.set()
    await asyncio.sleep(0.03)

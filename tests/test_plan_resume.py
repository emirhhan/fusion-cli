"""Checkpoint'ten devam ederken post-condition'ların yeniden ölçülmesi."""

from __future__ import annotations

from dataclasses import dataclass

from fusion_cli.core.checkpoint import WorkflowCheckpoint
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    RetrySafety,
    StepStatus,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore


@dataclass
class _Deps:
    tool_context: ToolContext
    checkpoint_store: JsonCheckpointStore
    conversation_id: str = "conv"
    verifier: object | None = None


def _plan() -> ExecutionPlan:
    step = PlanStep(
        step_id="create",
        goal="dosyayı oluştur",
        depends_on=(),
        expected_effects=("file:result.txt",),
        allowed_tool_families=("files",),
        success_criteria=("dosya var",),
        verification_hint="dosyayı oku",
        retry_safety=RetrySafety.SAFE,
        status=StepStatus.COMPLETED,
        attempts=1,
    )
    return ExecutionPlan(
        plan_id="resume-1",
        task="dosya oluştur",
        steps=(step,),
        status=PlanStatus.RUNNING,
    )


def _save(deps: _Deps):
    deps.checkpoint_store.save(
        WorkflowCheckpoint(
            plan=_plan(),
            root=str(deps.tool_context.root.resolve()),
            conversation_id=deps.conversation_id,
            completed_step_ids=("create",),
            updated_at=1.0,
        )
    )


async def test_gecerli_tamamlanmis_adim_yeniden_calistirilmaz(tmp_path):
    (tmp_path / "result.txt").write_text("ok", encoding="utf-8")
    deps = _Deps(ToolContext(root=tmp_path), JsonCheckpointStore(tmp_path / ".cp"))
    _save(deps)
    calls = 0

    async def agent(task, agent_deps, **kwargs):
        nonlocal calls
        del task, agent_deps, kwargs
        calls += 1
        return AgentOutcome(final_text="tamam", messages=[])

    result = await run_execution_plan("dosya oluştur", deps, agent)

    assert result.ok is True
    assert calls == 0


async def test_post_condition_bozulduysa_adim_yeniden_calistirilir(tmp_path):
    deps = _Deps(ToolContext(root=tmp_path), JsonCheckpointStore(tmp_path / ".cp"))
    _save(deps)
    calls = 0

    async def agent(task, agent_deps, **kwargs):
        nonlocal calls
        del task, kwargs
        calls += 1
        (agent_deps.tool_context.root / "result.txt").write_text("ok", encoding="utf-8")
        return AgentOutcome(final_text="tamam", messages=[], mutating_tool_calls_made=1)

    result = await run_execution_plan("dosya oluştur", deps, agent)

    assert result.ok is True
    assert calls == 1

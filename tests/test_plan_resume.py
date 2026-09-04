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


class _Publisher:
    def publish(self, event):
        del event


@dataclass
class _Deps:
    tool_context: ToolContext
    checkpoint_store: JsonCheckpointStore
    conversation_id: str = "conv"
    verifier: object | None = None
    publisher: object = _Publisher()


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


def _duraklamis_plan() -> ExecutionPlan:
    """Bütçe tükendiği için `blocked` bırakılmış bir adım ve ona bağlı bir adım."""
    ortak = {
        "depends_on": (),
        "expected_effects": ("file:result.txt",),
        "allowed_tool_families": ("files",),
        "success_criteria": ("dosya var",),
        "verification_hint": "dosyayı oku",
        "retry_safety": RetrySafety.SAFE,
    }
    return ExecutionPlan(
        plan_id="resume-2",
        task="dosya oluştur",
        steps=(
            PlanStep(
                step_id="create",
                goal="dosyayı oluştur",
                status=StepStatus.BLOCKED,
                attempts=1,
                **ortak,
            ),
            PlanStep(
                **{**ortak, "depends_on": ("create",)},
                step_id="finish",
                goal="işi bitir",
                status=StepStatus.PENDING,
            ),
        ),
        status=PlanStatus.PAUSED,
    )


async def test_butce_yuzunden_duraklayan_adim_devamda_yeniden_acilir(tmp_path):
    """Ölçüldü (Godot koşusu): 22 başarılı araç çağrısından sonra adım bütçesi doldu.

    Adım `blocked` bırakıldı, checkpoint kaydedildi — ama devam çalıştırıldığında
    plan "tamamlanmamış adımların bağımlılıkları hazır değil" diyerek kilitlendi:
    `blocked` adım hiç yeniden açılmıyordu ve ona bağlı adımlar da asla hazır
    olamıyordu. Duraklamanın anlamı "sonra devam" olmalı, "bir daha asla" değil.
    """
    deps = _Deps(ToolContext(root=tmp_path), JsonCheckpointStore(tmp_path / ".cp"))
    deps.checkpoint_store.save(
        WorkflowCheckpoint(
            plan=_duraklamis_plan(),
            root=str(deps.tool_context.root.resolve()),
            conversation_id=deps.conversation_id,
            completed_step_ids=(),
            updated_at=1.0,
        )
    )
    calisan: list[str] = []

    async def agent(task, agent_deps, **kwargs):
        del kwargs
        calisan.append("create" if "dosyayı oluştur" in task else "finish")
        (agent_deps.tool_context.root / "result.txt").write_text("ok", encoding="utf-8")
        return AgentOutcome(final_text="tamam", messages=[], mutating_tool_calls_made=1)

    result = await run_execution_plan("dosya oluştur", deps, agent)

    assert calisan == ["create", "finish"]
    assert result.ok is True

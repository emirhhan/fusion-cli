"""Dış mutasyon başlamadan kalıcı intent sınırı çalışmalıdır."""

import pytest

from fusion_cli.core.tools import AuthorizationScope, Tool, ToolEffect, ToolResult
from fusion_cli.core.types import ToolCall
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _execute
from fusion_cli.tools.registry import ToolRegistry
from tests.test_tool_contract_v2 import _deps


async def test_external_write_records_intent_before_executor(tmp_path):
    order = []

    class Recorder:
        async def prepare(self, call, tool, effect, scope):
            order.append("intent")

        async def finish(self, call_id, ok):
            order.append("response")

    registry = ToolRegistry()

    def write(args, context):
        order.append("write")
        return ToolResult("ack")

    registry.register(
        Tool(
            "server__write",
            "",
            {},
            write,
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
            scope_resolver=lambda _: AuthorizationScope("server", "account", "write", ("target",)),
        )
    )
    deps = _deps(tmp_path)
    deps.effect_recorder = Recorder()
    await _execute(
        ToolCall("call-1", "server__write", "{}"),
        {},
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
    )
    assert order == ["intent", "write", "response"]


async def test_new_input_during_intent_save_blocks_external_executor(tmp_path):
    order = []
    pending = {"value": False}

    class Recorder:
        async def prepare(self, *args):
            order.append("intent")
            pending["value"] = True

        async def finish(self, *args):
            order.append("response")

    registry = ToolRegistry()

    def write(args, context):
        order.append("write")
        return ToolResult("ack")

    registry.register(Tool("remote", "", {}, write, mutating=True, effect=ToolEffect.REMOTE_WRITE))
    deps = _deps(tmp_path)
    deps.effect_recorder = Recorder()
    deps.mutation_blocked_by_pending_input = lambda: pending["value"]
    result, _ = await _execute(
        ToolCall("call", "remote", "{}"),
        {},
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
    )
    assert not result.ok
    assert order == ["intent"]


async def test_real_checkpoint_survives_executed_response_loss_without_replay(tmp_path):
    from dataclasses import replace

    import pytest

    from fusion_cli.core.effects import EffectPhase
    from fusion_cli.core.execution_plan import ExecutionPlan, RetrySafety, StepStatus
    from fusion_cli.engines.agent.effect_checkpoint import EffectAdmissionError, PlanEffectRecorder
    from fusion_cli.engines.agent.plan_checkpoint import resume_plan
    from fusion_cli.engines.agent.plan_runner import _PlanRun
    from fusion_cli.engines.workflow.model import BudgetLedger, WorkflowBudget
    from tests.test_plan_repair import _deps as plan_deps
    from tests.test_plan_runner import _step

    step = replace(_step("send"), attempts=1, status=StepStatus.RUNNING)
    budget = WorkflowBudget(planning=2, per_step=4, recovery=2, final=2)
    run = _PlanRun(
        "iş",
        plan_deps(tmp_path),
        None,
        ExecutionPlan("external-intent", "iş", (step,)),
        budget,
        BudgetLedger(budget),
    )
    actor = _deps(tmp_path)
    actor.effect_recorder = PlanEffectRecorder(run, "send", 1)
    writes = []

    def write(args, context):
        saved = run.deps.checkpoint_store.load("external-intent")
        assert saved.effect_intents[0].phase is EffectPhase.IN_FLIGHT
        assert saved.plan.steps[0].retry_safety is RetrySafety.OBSERVE_FIRST
        writes.append("executed")
        raise TimeoutError("response lost")

    registry = ToolRegistry()
    registry.register(
        Tool(
            "remote",
            "",
            {},
            write,
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
            scope_resolver=lambda _: AuthorizationScope("server", "account", "send", ("target",)),
        )
    )
    result, _ = await _execute(
        ToolCall("first", "remote", "{}"),
        {"secret": "NOT_PERSISTED"},
        actor,
        registry,
        execution=ExecutionPolicy(is_web=False),
    )
    assert not result.ok
    saved = run.deps.checkpoint_store.load("external-intent")
    assert saved.effect_intents[0].phase is EffectPhase.AMBIGUOUS
    assert all(
        "NOT_PERSISTED" not in path.read_text() for path in (tmp_path / ".cp").glob("*.json")
    )
    resumed, _ = await resume_plan(saved, run.deps)
    assert resumed.steps[0].retry_safety is RetrySafety.OBSERVE_FIRST
    with pytest.raises(EffectAdmissionError):
        await _execute(
            ToolCall("second", "remote", "{}"),
            {},
            actor,
            registry,
            execution=ExecutionPolicy(is_web=False),
        )
    assert writes == ["executed"]


@pytest.mark.parametrize(
    "targets,action", [(("b", "a"), "write"), (("b", "c"), "write"), (("a",), "delete")]
)
async def test_ambiguous_resource_overlap_cannot_be_rewritten(tmp_path, targets, action):
    from dataclasses import replace

    from fusion_cli.core.execution_plan import ExecutionPlan, StepStatus
    from fusion_cli.engines.agent.effect_checkpoint import EffectAdmissionError, PlanEffectRecorder
    from fusion_cli.engines.agent.plan_runner import _PlanRun
    from fusion_cli.engines.workflow.model import BudgetLedger, WorkflowBudget
    from tests.test_plan_repair import _deps as plan_deps
    from tests.test_plan_runner import _step

    step = replace(_step("send"), attempts=1, status=StepStatus.RUNNING)
    budget = WorkflowBudget(planning=2, per_step=4, recovery=2, final=2)
    run = _PlanRun(
        "iş",
        plan_deps(tmp_path),
        None,
        ExecutionPlan("collision", "iş", (step,)),
        budget,
        BudgetLedger(budget),
    )
    recorder = PlanEffectRecorder(run, "send", 1)
    tool = Tool(
        "remote", "", {}, lambda *_: ToolResult(""), mutating=True, effect=ToolEffect.REMOTE_WRITE
    )
    await recorder.prepare(
        ToolCall("first", "remote", "{}"),
        tool,
        tool.effect,
        AuthorizationScope("server", "account", "write", ("a", "b")),
    )
    await recorder.finish("first", False)
    with pytest.raises(EffectAdmissionError):
        await recorder.prepare(
            ToolCall("second", "remote", "{}"),
            tool,
            tool.effect,
            AuthorizationScope("server", "account", action, targets),
        )


async def test_workflow_child_external_executor_sees_durable_intent(tmp_path, monkeypatch):
    from dataclasses import replace

    from fusion_cli.core.effects import EffectPhase
    from fusion_cli.core.execution_plan import ExecutionPlan, StepStatus
    from fusion_cli.engines.agent.effect_checkpoint import PlanEffectRecorder
    from fusion_cli.engines.agent.loop import run_agent
    from fusion_cli.engines.agent.plan_runner import _PlanRun
    from fusion_cli.engines.agent.team import SubTask, run_subagent
    from fusion_cli.engines.workflow.model import BudgetLedger, WorkflowBudget
    from fusion_cli.memory.checkpoint_store import JsonCheckpointStore
    from tests.agent_harness import install_provider
    from tests.fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from tests.test_plan_runner import _step
    from tests.test_team import _deps as team_deps

    install_provider(
        monkeypatch,
        ScriptedProvider(
            [
                model_result("", tool_calls=(tool_call("remote_write"),)),
                model_result("Uzak işlem sonucu gerçek araç kaydı üzerinden değerlendirildi."),
            ]
        ),
    )
    parent = team_deps(tmp_path, RecordingSink())
    parent.checkpoint_store = JsonCheckpointStore(tmp_path / ".cp")
    parent.conversation_id = "conv"
    step = replace(_step("send"), attempts=1, status=StepStatus.RUNNING)
    budget = WorkflowBudget(planning=2, per_step=4, recovery=2, final=2)
    run = _PlanRun(
        "iş",
        parent,
        None,
        ExecutionPlan("child-intent", "iş", (step,)),
        budget,
        BudgetLedger(budget),
    )
    parent.effect_recorder = PlanEffectRecorder(run, "send", 1)
    writes = []

    def write(args, context):
        saved = parent.checkpoint_store.load("child-intent")
        assert saved is not None and saved.effect_intents[0].phase is EffectPhase.IN_FLIGHT
        writes.append("executed")
        return ToolResult("ack")

    parent.base_registry = ToolRegistry()
    parent.base_registry.register(
        Tool(
            "remote_write",
            "",
            {},
            write,
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
            scope_resolver=lambda _: AuthorizationScope("server", "account", "write", ("target",)),
        )
    )
    await run_subagent(parent, SubTask("Uzak hedefe yaz"), depth=0, run_agent=run_agent)
    assert writes == ["executed"]
    assert (
        parent.checkpoint_store.load("child-intent").effect_intents[0].phase
        is EffectPhase.RESPONDED
    )

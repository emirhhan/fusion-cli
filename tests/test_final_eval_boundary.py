"""Bütün dal eval sınırı: uygulanabilir bütçe ve gerçek V2 köken zinciri."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from evals import agent_runner, direct_runner
from evals.executor import AgentTaskExecutor
from evals.profiles import EvalProfile, build_run_metadata, build_runner
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion, TaskBudget

from fusion_cli.core.clock import SystemClock
from fusion_cli.core.types import CompletionRequest, Message
from fusion_cli.engines.agent.loop import AgentOutcome
from tests.fakes import ScriptedProvider, make_config, model_result

PROFILES = (EvalProfile.FUSION_FULL, EvalProfile.FUSION_MINIMAL, EvalProfile.DIRECT)


def simple_task(budget):
    return EvalTask(
        "ordinary", "tamam", SuccessCriterion(CriterionKind.KEYWORD, keyword="tamam"), budget=budget
    )


@pytest.mark.parametrize("profile", PROFILES)
async def test_budgeted_factory_executor_enforces_or_rejects_before_calls(
    tmp_path, monkeypatch, profile
):
    calls, cancelled = [], []

    async def slow(request, deps, **kwargs):
        calls.append("agent")
        try:
            await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return AgentOutcome("tamam", [])

    class Provider:
        async def complete(self, request):
            calls.append("direct")
            await asyncio.sleep(0.08)
            return model_result("<!doctype html><html>tamam</html>")

    monkeypatch.setattr(agent_runner, "run_agent", slow)
    monkeypatch.setattr(direct_runner, "build_direct_provider", lambda *args: Provider())
    config = make_config(memory_dir=tmp_path / "memory")
    task = simple_task(TaskBudget(1, 0.01))
    if profile is not EvalProfile.FUSION_FULL:
        with pytest.raises(ValueError, match="bütçe"):
            build_runner(profile, config, task=task)
        assert calls == []
    else:
        result = await AgentTaskExecutor(
            build_runner(profile, config, task=task), workspace_root=tmp_path, clock=SystemClock()
        ).run(task)
        assert cancelled == [True] and result.claimed_success is False


@pytest.mark.parametrize("profile", (EvalProfile.FUSION_MINIMAL, EvalProfile.DIRECT))
def test_unsupported_task_budget_cannot_be_recorded_as_applied(tmp_path, profile):
    config = make_config(memory_dir=tmp_path / "memory")
    with pytest.raises(ValueError, match="bütçe"):
        build_run_metadata(
            suite=tmp_path / "not_loaded.yaml",
            tasks=(simple_task(TaskBudget(1, 0.01)),),
            profile=profile,
            config=config,
            repeat=1,
            seed=None,
            calls=(),
        )


@pytest.mark.parametrize("profile", PROFILES)
async def test_unbudgeted_legacy_profiles_still_run(tmp_path, monkeypatch, profile):
    async def answer(request, deps, **kwargs):
        return AgentOutcome("tamam", [])

    monkeypatch.setattr(agent_runner, "run_agent", answer)
    monkeypatch.setattr(
        direct_runner,
        "build_direct_provider",
        lambda *args: ScriptedProvider([model_result("<!doctype html><html>tamam</html>")]),
    )
    task = simple_task(None)
    runner = build_runner(profile, make_config(memory_dir=tmp_path / "memory"), task=task)
    result = await AgentTaskExecutor(runner, workspace_root=tmp_path, clock=SystemClock()).run(task)
    assert result.claimed_success and "tamam" in result.output_text


async def test_full_task_call_cap_counts_all_provider_roles(tmp_path, monkeypatch):
    from fusion_cli.providers.eventing import EventingProvider

    provider = ScriptedProvider([model_result("tamam")] * 3)

    async def invoke(request, deps, **kwargs):
        for role in ("agent", "judge", "learning"):
            await EventingProvider(provider, publisher=deps.publisher, role=role).complete(
                CompletionRequest((), 0, 10, 1)
            )
        return AgentOutcome("tamam", [])

    monkeypatch.setattr(agent_runner, "run_agent", invoke)
    task = simple_task(TaskBudget(1, 1))
    runner = build_runner(
        EvalProfile.FUSION_FULL, make_config(memory_dir=tmp_path / "memory"), task=task
    )
    result = await AgentTaskExecutor(runner, workspace_root=tmp_path, clock=SystemClock()).run(task)
    assert provider.calls == result.model_calls == 1
    assert result.claimed_success is False


@pytest.mark.parametrize("profile", (EvalProfile.FUSION_FULL, EvalProfile.FUSION_MINIMAL))
@pytest.mark.parametrize("origin_kind", ("direct", "unknown", "quoted"))
async def test_real_eval_builder_adapter_v2_origin_and_scope(
    tmp_path, monkeypatch, profile, origin_kind
):
    from fusion_cli.core.web_provenance import safe_observed_identifier

    config = make_config(memory_dir=tmp_path / "memory", runtime={"emulation_protocol": "v2"})
    results, contexts, scopes = [], [], []
    install_v2_boundary(monkeypatch, tmp_path, origin_kind, results, contexts, scopes)
    task = simple_task(None)
    runner = build_runner(profile, config, task=task)
    execution = await AgentTaskExecutor(
        runner, workspace_root=tmp_path / "work", clock=SystemClock()
    ).run(task)
    context = contexts[0]
    result = results[0]
    assert safe_observed_identifier(context.session_id) == context.session_id
    assert scopes[0][0] == context.session_id == scopes[0][1]
    assert scopes[0][2] == (tmp_path / "work" / task.id).resolve()
    from fusion_cli.core.events import ModelCallStarted

    calls = [event for event in execution.trace_events if isinstance(event, ModelCallStarted)]
    assert calls and {event.session_id for event in calls} == {context.session_id}
    assert {event.turn_id for event in calls} == {context.turn_id}
    if origin_kind == "direct":
        assert result.web_provenance.has_current_assistant_origin(context)
        assert not result.parse_warnings and [call.name for call in result.tool_calls] == [
            "write_file"
        ]
    else:
        assert (
            any(warning.blocks_mutation for warning in result.parse_warnings)
            or not result.tool_calls
        )
        if origin_kind == "quoted":
            assert not result.tool_calls


def install_v2_boundary(monkeypatch, tmp_path, origin_kind, results, contexts, scopes):
    from fusion_cli.core.event_scope import TurnPublisher
    from fusion_cli.core.model_capability import ToolSupport
    from fusion_cli.core.tool_emulation import render_call
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.execution_policy import policy_for
    from fusion_cli.providers.eventing import EventingProvider
    from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn
    from tests.test_web_tool_provenance import observed_origin

    async def transport(credential, messages, model, *, context):
        contexts.append(context.web_call_context)
        origin = (
            None
            if origin_kind == "unknown"
            else replace(
                observed_origin(), call_context=context.web_call_context, content_kind=origin_kind
            )
        )
        return WebTurn(
            render_call({"name": "write_file", "arguments": {"path": "a.txt", "content": "ok"}}),
            provenance=origin,
        )

    async def invoke(request, deps, **kwargs):
        deps.attempt_id = "actual-turn"
        deps.publisher = TurnPublisher(
            deps.publisher, session_id=deps.conversation_id, attempt_id=deps.attempt_id
        )
        checkpoint_scope(deps, tmp_path, scopes)
        adapter = WebProviderAdapter(
            model=deps.config.agent.model,
            credential=WebSessionCredential(),
            transport=transport,
            tool_support=ToolSupport.EMULATED,
        )
        provider = EventingProvider(
            adapter, publisher=deps.publisher, role="agent", call_id_factory=lambda: "actual-call"
        )
        monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
        result = await loop._call_model(
            [Message("user", request)],
            deps,
            deps.base_registry,
            state=loop._State(),
            execution=policy_for(deps.config, deps.config.agent, request),
        )
        results.append(result)
        return AgentOutcome("tamam", [])

    monkeypatch.setattr(agent_runner, "run_agent", invoke)


def checkpoint_scope(deps, tmp_path, scopes):
    from fusion_cli.core.checkpoint import WorkflowCheckpoint
    from fusion_cli.core.execution_plan import ExecutionPlan
    from fusion_cli.memory.checkpoint_store import JsonCheckpointStore

    store = JsonCheckpointStore(
        tmp_path / "checkpoints", root=deps.tool_context.root, conversation_id=deps.conversation_id
    )
    checkpoint = WorkflowCheckpoint(
        ExecutionPlan("eval-plan", "iş", ()),
        str(deps.tool_context.root.resolve()),
        deps.conversation_id,
        (),
        deps.clock.now(),
    )
    store.save(checkpoint)
    loaded = store.load("eval-plan")
    scopes.append((deps.conversation_id, loaded.conversation_id, deps.tool_context.root))


@pytest.mark.parametrize("command", ("run", "matrix"))
@pytest.mark.parametrize("profile", (EvalProfile.FUSION_MINIMAL, EvalProfile.DIRECT))
def test_cli_rejects_unsupported_budget_without_provider_or_report(
    tmp_path, monkeypatch, capsys, command, profile
):
    import yaml
    from evals import cli
    from evals.loader import task_to_mapping

    suite = tmp_path / "suite.yaml"
    suite.write_text(yaml.safe_dump({"tasks": [task_to_mapping(simple_task(TaskBudget(1, 0.01)))]}))
    monkeypatch.setattr(cli, "load_config", lambda: make_config(memory_dir=tmp_path / "memory"))
    monkeypatch.setattr(
        cli, "build_runner", lambda *args, **kwargs: pytest.fail("Sağlayıcıya ulaşılamaz")
    )
    target = tmp_path / "report"
    args = [command, str(suite), "--workspace", str(tmp_path / "work")]
    args += (
        ["--out", str(target), "--profile", profile.value]
        if command == "run"
        else ["--out-dir", str(target)]
    )
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    assert "bütçe" in capsys.readouterr().err
    assert not target.exists()


def test_eval_session_scope_is_deterministic_and_root_stays_separate(tmp_path):
    publisher = agent_runner._CountingPublisher(agent_runner._NullPublisher())
    runner = build_runner(EvalProfile.FUSION_FULL, make_config(memory_dir=tmp_path / "memory"))
    first = runner._dependencies(tmp_path, publisher, False)
    same = runner._dependencies(tmp_path / ".", publisher, False)
    other = runner._dependencies(tmp_path / "different", publisher, False)
    assert first.conversation_id == same.conversation_id != other.conversation_id
    assert first.tool_context.root == tmp_path
    assert str(tmp_path) not in first.conversation_id

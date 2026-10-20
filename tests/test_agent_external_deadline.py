"""API motoru dış süre otoritesini korur; geç yanıt araç başlatmaz."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.core.turn_deadline import TurnDeadline
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)
from .test_turn_deadline import FakeClock


class Publisher:
    def __init__(self):
        self.sink = RecordingSink()

    def publish(self, event):
        self.sink.handle(event)


def deps_for(root, deadline, **config_args):
    return AgentDeps(
        config=make_config(memory_dir=root / "memory", **config_args),
        publisher=Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=root),
        deadline=deadline,
    )


async def test_expired_external_deadline_stops_api_before_first_provider_call(
    tmp_path, monkeypatch
):
    clock = FakeClock()
    deadline = TurnDeadline.from_duration(5, clock)
    clock.value = 6
    provider = ScriptedProvider([model_result("olmamalı")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    deps = deps_for(tmp_path, deadline)
    result = await run_agent("merhaba", deps, self_review=False, verify=False)
    assert not result.ok
    assert result.stop_reason == "deadline"
    assert provider.calls == 0


async def test_late_provider_tool_result_does_not_mutate_after_external_deadline(
    tmp_path, monkeypatch
):
    clock = FakeClock()

    class LateProvider(ScriptedProvider):
        def _next(self, request):
            clock.value = 6
            return super()._next(request)

    provider = LateProvider(
        [model_result(tool_calls=[tool_call("write_file", path="late.txt", content="late")])]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    deps = deps_for(tmp_path, TurnDeadline.from_duration(5, clock))
    result = await run_agent("dosya yaz", deps, self_review=False, verify=False)
    assert not result.ok
    assert result.stop_reason == "deadline"
    assert not (tmp_path / "late.txt").exists()


async def test_retry_wait_respects_remaining_deadline_without_next_provider_call(
    tmp_path, monkeypatch
):
    clock = FakeClock()
    provider = ScriptedProvider(
        [model_result(ok=False, error="temporary 503"), model_result("olmamalı")]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    waits = []

    async def sleep(seconds):
        waits.append(seconds)
        clock.value += seconds

    monkeypatch.setattr(loop, "_retry_sleep", sleep)
    deps = deps_for(
        tmp_path, TurnDeadline.from_duration(1, clock), runtime={"model_retry_attempts": 2}
    )
    result = await run_agent("merhaba", deps, self_review=False, verify=False)
    assert waits == [1]
    assert provider.calls == 1
    assert not result.ok and result.stop_reason == "deadline"


async def test_nested_agent_uses_original_deadline_and_shared_budget(tmp_path, monkeypatch):
    clock = FakeClock()
    provider = ScriptedProvider([model_result("ilk"), model_result("olmamalı")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    deps = deps_for(tmp_path, TurnDeadline.from_duration(5, clock))
    assert (await run_agent("merhaba", deps, self_review=False, verify=False)).ok
    original = deps.budget
    clock.value = 6
    result = await run_agent("devam", deps, depth=1, internal=True, self_review=False, verify=False)
    assert deps.budget is original
    assert not result.ok and result.stop_reason == "deadline"
    assert provider.calls == 1


async def test_cli_agent_entry_preserves_typed_deadline(tmp_path, monkeypatch):
    from fusion_cli.cli import session
    from fusion_cli.engines.agent.loop import AgentOutcome

    seen = []

    async def run(task, deps, **kwargs):
        seen.append(deps.deadline)
        return AgentOutcome(final_text="bitti", messages=[])

    monkeypatch.setattr(session, "run_agent", run)
    deadline = TurnDeadline.from_duration(5, FakeClock())
    await session.run_agent_task(
        "merhaba",
        make_config(memory_dir=tmp_path / "memory"),
        sinks=(),
        prompter_factory=lambda drain: AlwaysApprove(),
        root=tmp_path,
        interactive=False,
        deadline=deadline,
    )
    assert seen == [deadline]


async def test_deadline_stops_later_tool_in_same_batch(tmp_path, monkeypatch):
    from fusion_cli.core.tools import Tool, ToolResult

    clock = FakeClock()
    provider = ScriptedProvider(
        [
            model_result(
                tool_calls=[
                    tool_call("consume_time"),
                    tool_call("write_file", path="late.txt", content="late"),
                ]
            ),
            model_result("olmamalı"),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    deps = deps_for(tmp_path, TurnDeadline.from_duration(5, clock))

    async def consume(args, context):
        clock.value = 6
        return ToolResult(output="süre geçti")

    deps.base_registry.register(
        Tool(
            name="consume_time",
            description="Test saati",
            parameters={"type": "object"},
            run=consume,
        )
    )
    result = await run_agent("araçları çalıştır", deps, self_review=False, verify=False)
    assert not result.ok and result.stop_reason == "deadline"
    assert not (tmp_path / "late.txt").exists()
    assert provider.calls == 1
    skipped = [message for message in result.messages if message.role == "tool"]
    assert len(skipped) == 2 and skipped[-1].ok is False


async def test_approval_expiry_blocks_tool_start_and_write(tmp_path, monkeypatch):
    from fusion_cli.core.events import ToolStarted
    from fusion_cli.engines.agent.approval import Decision

    clock = FakeClock()
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("write_file", path="late.txt", content="late")]),
            model_result("olmamalı"),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    deps = deps_for(tmp_path, TurnDeadline.from_duration(5, clock))

    class DelayedApproval:
        async def decide(self, request):
            clock.value = 5
            return Decision.ALLOW

    deps.policy = DelayedApproval()
    result = await run_agent("dosya yaz", deps, self_review=False, verify=False)
    assert not result.ok and result.stop_reason == "deadline"
    assert not (tmp_path / "late.txt").exists()
    assert not any(isinstance(event, ToolStarted) for event in deps.publisher.sink.events)
    assert provider.calls == 1

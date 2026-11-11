"""Task entry points enforce the user's noninteractive preference."""

from __future__ import annotations

import io
from dataclasses import replace
from types import SimpleNamespace

from rich.console import Console

from fusion_cli.appserver.session import AppSession
from fusion_cli.cli import session as cli_session
from fusion_cli.cli.repl import loop as repl_loop
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.core.concurrency import BackgroundTasks
from fusion_cli.core.events import ToolOutcome
from fusion_cli.core.tools import Tool, ToolResult
from fusion_cli.engines import agent
from fusion_cli.engines.agent import approval, loop, team_tools, workflow_tools
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.mcp_bridge.elicitation import elicitation_asker_scope, registered_elicitation_asker
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.registry import ToolRegistry

from .fakes import make_config, tool_call
from .test_agent_lessons import _deps


def test_config_preserves_interaction_by_default_and_accepts_opt_out(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("runtime: {}\n", encoding="utf-8")
    assert load_config(path).runtime.interaction_prompts is True

    path.write_text("runtime:\n  interaction_prompts: false\n", encoding="utf-8")
    assert load_config(path).runtime.interaction_prompts is False


async def test_appserver_task_and_child_policies_use_noninteractive_setting(tmp_path, monkeypatch):
    flags = []
    real_policy = approval.build_policy

    def build(*args, **kwargs):
        flags.append(kwargs.pop("interaction_prompts", True))
        return real_policy(*args, **kwargs)

    async def run_agent(task, deps, **kwargs):
        assert deps.asker is None
        assert deps.interactive is False
        assert registered_elicitation_asker() is None
        assert deps.policy_factory is not None and deps.policy_factory() is not None
        assert deps.policy_for_mode is not None
        deps.policy_for_mode(approval.ApprovalMode.SECURITY)
        assert deps.auto_review.on_fallback is not None
        deps.auto_review.on_fallback()
        assert deps.approval_mode() is approval.ApprovalMode.AUTO
        return loop.AgentOutcome("Done", [], 0, ok=True)

    monkeypatch.setattr(cli_session, "build_policy", build)
    monkeypatch.setattr(cli_session, "run_agent", run_agent)
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    config = session._state.config
    session._state.config = replace(
        config,
        runtime=replace(config.runtime, interaction_prompts=False),
        mcp_servers=(),
    )
    session._state.approval = approval.ApprovalMode.AUTO
    parent_asker = SimpleNamespace()
    try:
        with elicitation_asker_scope(parent_asker):
            assert (await session._run_turn("Complete the task"))["ok"]
            assert registered_elicitation_asker() is parent_asker
    finally:
        await session.close()

    assert flags == [False, False, False]


async def test_repl_task_and_child_policies_use_noninteractive_setting(tmp_path, monkeypatch):
    flags = []
    real_policy = approval.build_policy

    def build(*args, **kwargs):
        flags.append(kwargs.pop("interaction_prompts", True))
        return real_policy(*args, **kwargs)

    async def run_agent(task, deps, **kwargs):
        assert deps.asker is None
        assert deps.interactive is False
        assert registered_elicitation_asker() is None
        assert deps.policy_for_mode is not None
        deps.policy_for_mode(approval.ApprovalMode.SECURITY)
        return loop.AgentOutcome("Done", [], 0, ok=True)

    monkeypatch.setattr(approval, "build_policy", build)
    monkeypatch.setattr(agent, "run_agent", run_agent)
    state = ReplState(
        config=make_config(runtime={"interaction_prompts": False}),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "home",
    )
    parent_asker = SimpleNamespace()
    with elicitation_asker_scope(parent_asker):
        await repl_loop._agent_turn(
            "Complete the task", state, Console(file=io.StringIO()), BackgroundTasks()
        )
        assert registered_elicitation_asker() is parent_asker

    assert flags == [False, False]


async def test_stale_ask_user_is_hidden_and_blocked_before_dispatch(tmp_path):
    asked = []

    async def ask(*args):
        asked.append(args)
        return "yes"

    deps = _deps(tmp_path)
    deps.config = make_config(runtime={"interaction_prompts": False})
    deps.asker = SimpleNamespace(ask=ask)
    offered = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    assert offered.get("ask_user") is None

    async def stale_ask(args, context):
        await ask(args["question"])
        return ToolResult("yes")

    stale = ToolRegistry()
    stale.register(Tool("ask_user", "", {"type": "object"}, stale_ask))
    result, outcome = await loop._execute(
        tool_call("ask_user", question="Continue?"),
        {"question": "Continue?"},
        deps,
        stale,
        execution=ExecutionPolicy(is_web=False),
    )
    assert not result.ok
    assert outcome is ToolOutcome.BLOCKED
    assert asked == []


async def test_required_orchestration_confirmations_block_when_prompts_are_disabled(tmp_path):
    deps = _deps(tmp_path)
    deps.config = make_config(
        runtime={
            "interaction_prompts": False,
            "agent_team_confirm": True,
            "dynamic_workflow_confirm_agents": 3,
        }
    )
    assert not await team_tools._confirmed(deps, SimpleNamespace())
    assert not await workflow_tools._confirmed(deps, SimpleNamespace(), 3, 1)
    assert await workflow_tools._confirmed(deps, SimpleNamespace(), 2, 1)

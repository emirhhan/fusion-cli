"""Desktop state can change without a successful Fusion mutation."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import Tool, ToolResult
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.tools.registry import ToolRegistry

from .fakes import RecordingSink, tool_call
from .test_agent_loop import _deps


@pytest.mark.parametrize(
    "name", ["desktop_background_inspect", "desktop_screenshot", "desktop_background_windows"]
)
async def test_desktop_observation_reads_live_state_after_external_change(tmp_path, name):
    deps = _deps(tmp_path, RecordingSink())
    deps.budget = loop._new_budget(deps.config)
    state = loop._State()
    registry = ToolRegistry()
    observed = []
    external_state = {"value": "before"}

    async def observe(args, context):
        observed.append(external_state["value"])
        return ToolResult(external_state["value"])

    registry.register(Tool(name, "", {"type": "object"}, observe))
    messages = []
    for value in ["before", "before", "after", "new fingerprint", "latest", "final"]:
        external_state["value"] = value
        await loop._run_tools(
            (tool_call(name),),
            messages,
            deps,
            registry,
            state,
            execution=ExecutionPolicy(is_web=False),
        )

    assert observed == ["before", "before", "after", "new fingerprint", "latest", "final"]
    assert [message.content for message in messages] == observed

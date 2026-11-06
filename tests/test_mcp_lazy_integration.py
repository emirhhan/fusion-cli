"""Real coordinator integration with active runtime, model requests and executor."""

from dataclasses import replace

import pytest

from fusion_cli.config.models import McpServerConfig
from fusion_cli.core.tools import Tool, ToolContext, ToolEffect, ToolResult
from fusion_cli.core.types import StreamDone
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.mcp_bridge.discovery import McpDiscovery
from fusion_cli.tools import ToolRegistry
from tests.fakes import AlwaysApprove, make_config, model_result, tool_call


@pytest.mark.parametrize("toolsearch", ["false", "true"])
async def test_real_catalog_selected_discovery_real_runtime_request_executor(
    tmp_path, monkeypatch, toolsearch
):
    monkeypatch.setenv("ENABLE_TOOL_SEARCH", toolsearch)
    from fusion_cli.mcp_bridge import pool

    boundaries = []
    business = []

    async def ensure(configs, registry, **kwargs):
        boundaries.append(kwargs["selected_names"])

        def read(args, context):
            business.append("called")
            return ToolResult(output="synthetic record 42")

        registry.register_or_replace(
            Tool(
                name="mcp__opaque_a__read",
                description="Real selected read",
                parameters={"type": "object", "properties": {}},
                run=read,
                mutating=True,
                effect=ToolEffect.REMOTE_READ,
            )
        )
        return ("mcp__opaque_a__read",)

    monkeypatch.setattr(pool, "ensure_mcp_tools", ensure)
    cfg = replace(
        make_config(),
        mcp_servers=(
            McpServerConfig(name="opaque_a", command="never-start"),
            McpServerConfig(name="unrelated", command="never-start2"),
        ),
    )
    calls = []

    class Publisher:
        def publish(self, e):
            pass

    class Provider:
        async def stream(self, request):
            names = {t["function"]["name"] for t in request.tools}
            calls.append(names)
            if len(calls) == 1:
                assert not boundaries
                result = model_result(tool_calls=(tool_call("DiscoverMcpTools"),))
            elif len(calls) == 2:
                assert not boundaries
                result = model_result(
                    tool_calls=(tool_call("DiscoverMcpTools", server="opaque_a"),)
                )
            elif len(calls) == 3:
                assert "mcp__opaque_a__read" in names
                result = model_result(tool_calls=(tool_call("mcp__opaque_a__read"),))
            else:
                result = model_result(text="The selected service record is 42.")
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: Provider())
    deps = loop.AgentDeps(
        config=cfg,
        publisher=Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=ToolRegistry(),
    )
    owner = McpDiscovery(lambda: deps.config, root=tmp_path)
    deps.mcp_discovery = owner
    outcome = await loop.run_agent(
        "Retrieve the requested record from opaque_a configured service",
        deps,
        self_review=False,
        step_limit=5,
    )
    assert outcome.ok
    assert boundaries == [frozenset({"opaque_a"})]
    assert business == ["called"]
    assert deps.base_registry.get("mcp__opaque_a__read") is None


@pytest.mark.parametrize("strict", [False, True])
async def test_root_without_mcp_trusted_inline_child_discovers_real_tool_same_turn(
    tmp_path, monkeypatch, strict
):
    from fusion_cli.engines.agent import team
    from fusion_cli.mcp_bridge import pool
    from fusion_cli.mcp_bridge.discovery import McpDiscovery
    from tests.test_inline_lazy_mcp import _Client, _inline

    deps, persona = _inline(tmp_path)
    deps.config = replace(deps.config, mcp_servers=())
    deps.mcp_discovery = McpDiscovery(lambda: deps.config, root=tmp_path)
    if strict:
        persona = replace(persona, tools=frozenset({"mcp__opaque__read"}))
    monkeypatch.setattr(team, "resolve_persona", lambda *a: persona)
    _Client.starts, _Client.closes, _Client.calls = [], [], []
    monkeypatch.setattr(pool, "McpClient", _Client)
    requests = []

    class Provider:
        async def stream(self, request):
            names = {item["function"]["name"] for item in request.tools}
            requests.append(names)
            if len(requests) == 1 and not strict:
                assert _Client.starts == []
                result = model_result(tool_calls=(tool_call("DiscoverMcpTools", server="opaque"),))
            elif len(requests) == (1 if strict else 2):
                assert "mcp__opaque__read" in names
                if strict:
                    assert "DiscoverMcpTools" not in names and "WaitForMcpServers" not in names
                result = model_result(tool_calls=(tool_call("mcp__opaque__read"),))
            else:
                result = model_result(text="The configured record is child-command.")
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: Provider())
    result = await team.run_subagent(
        deps,
        team.SubTask("Retrieve the configured service record", persona="reader"),
        depth=0,
        run_agent=loop.run_agent,
    )
    assert result.ok
    assert _Client.starts == ["child-command"]
    assert _Client.calls == ["child-command"]
    assert _Client.closes == ["child-command"]
    assert deps.config.mcp_servers == ()


@pytest.mark.parametrize("business", [True, False])
@pytest.mark.parametrize("discovery_mode", ["enabled", "absent", "denied", "disabled"])
async def test_pending_preflight_wait_rebinds_active_runtime_and_keeps_metadata_untrusted(
    tmp_path, monkeypatch, business, discovery_mode
):
    import asyncio
    from types import SimpleNamespace

    from fusion_cli.engines.agent import learning
    from fusion_cli.engines.agent.execution_policy import policy_for
    from fusion_cli.mcp_bridge import pool
    from fusion_cli.mcp_bridge.discovery import prepare_mcp_turn

    done = asyncio.create_task(asyncio.sleep(0))
    await done
    count = 0
    client = SimpleNamespace(server_instructions=lambda _: "Untrusted synthetic usage")
    target = SimpleNamespace(
        connecting_tasks=lambda: {"opaque": done},
        connected_client=lambda name: client if count > 1 else None,
    )
    monkeypatch.setattr(pool, "_POOL", target)

    async def ensure(configs, registry, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return ()
        registry.register_or_replace(
            Tool(
                "mcp__opaque__read",
                "Real read",
                {},
                lambda a, c: ToolResult(output="business record"),
                effect=ToolEffect.REMOTE_READ,
            )
        )
        return ("mcp__opaque__read",)

    monkeypatch.setattr(pool, "ensure_mcp_tools", ensure)
    config = replace(make_config(), mcp_servers=(McpServerConfig("opaque", command="never-start"),))
    deps = loop.AgentDeps(
        config=config,
        publisher=SimpleNamespace(publish=lambda e: None),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=ToolRegistry(),
    )
    allowed = {"WaitForMcpServers", "mcp__opaque__read"}
    if discovery_mode != "absent":
        allowed.add("DiscoverMcpTools")
    if discovery_mode == "disabled":
        deps.config = replace(
            config, runtime=replace(config.runtime, disabled_tools=("DiscoverMcpTools",))
        )
    denied = frozenset({"DiscoverMcpTools"}) if discovery_mode == "denied" else frozenset()
    owner, _ = await prepare_mcp_turn("Retrieve opaque records", deps, allowed=allowed)
    assert deps.base_registry.get("WaitForMcpServers")
    assert not deps.mcp_external_content
    seen = []

    class Provider:
        async def stream(self, request):
            names = {tool["function"]["name"] for tool in request.tools}
            seen.append(names)
            if len(seen) == 1:
                assert "WaitForMcpServers" in names
                if discovery_mode != "enabled":
                    assert "DiscoverMcpTools" not in names
                result = model_result(tool_calls=(tool_call("WaitForMcpServers"),))
            elif len(seen) == 2 and business:
                assert "mcp__opaque__read" in names
                assert "WaitForMcpServers" not in names
                result = model_result(tool_calls=(tool_call("mcp__opaque__read"),))
            else:
                result = model_result(text="The configured record is available.")
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: Provider())
    try:
        outcome = await loop.run_agent(
            "Retrieve opaque records",
            deps,
            allowed_tools=allowed,
            denied_tools=denied,
            self_review=False,
            step_limit=4,
        )
        assert deps.base_registry.get("mcp__opaque__read") is None
        evidence = deps.require_budget().successful_tool_evidence
        assert all(name != "WaitForMcpServers" for name, _, _ in evidence)
        assert learning.reads_external_content(
            [use for use in outcome.tool_uses if use.name == "WaitForMcpServers"]
        )
        assert deps.mcp_external_content
        if not business:
            execution = replace(
                policy_for(config, config.agent, "Count records"),
                required_effect="bulk_count",
                requires_tool_evidence=True,
            )
            assert not loop._tool_evidence_satisfied(execution, deps.require_budget())
    finally:
        owner.close()

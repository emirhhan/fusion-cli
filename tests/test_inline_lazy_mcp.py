"""Inline agent MCP configurations retain private transport and publication ownership."""

import asyncio
from dataclasses import replace
from typing import ClassVar

import pytest

from fusion_cli.cli.session import agent_mcp_scope
from fusion_cli.config.models import McpServerConfig
from fusion_cli.core.tools import Tool, ToolEffect, ToolResult
from fusion_cli.engines.agent import loop, team
from fusion_cli.engines.agent.agent_runtime_hooks import child_mcp_scope
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.mcp_bridge import pool as pool_module
from fusion_cli.mcp_bridge.discovery import McpDiscovery
from fusion_cli.mcp_bridge.pool import McpToolPool
from fusion_cli.mcp_bridge.types import McpConnectionStatus
from fusion_cli.tools import ToolRegistry

from .test_system_prompt_layers import _deps


def _inline(tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.home = tmp_path / "home"
    definition = deps.home / ".claude/agents/reader.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("Read configured service records.")
    deps.config = replace(
        deps.config,
        mcp_servers=(
            McpServerConfig("opaque", command="parent-command", env_names=("PARENT_SECRET",)),
            McpServerConfig("other", command="never-start-other"),
        ),
    )
    deps.mcp_connector = agent_mcp_scope
    deps.mcp_discovery = McpDiscovery(lambda: deps.config, root=tmp_path)
    persona = team.Persona(
        "reader",
        "Reader",
        "Read",
        "gray",
        source="claude",
        definition_path=definition,
        inline_mcp_servers=(
            McpServerConfig(
                "opaque",
                command="child-command",
                env_names=("INLINE_SECRET",),
                token_env="INLINE_TOKEN",
                env_literals=(("INLINE_LITERAL", "private-value"),),
            ),
        ),
    )
    return deps, persona


async def test_builtin_inline_child_catalog_is_local_and_masks_full_config(tmp_path, monkeypatch):
    deps, persona = _inline(tmp_path)
    parent_owner, original_registry = deps.mcp_discovery, deps.base_registry
    deps.base_registry.register_or_replace(
        Tool(
            "mcp__opaque__stale_parent",
            "Parent service tool",
            {},
            lambda a, c: ToolResult(output="must not call parent's overridden credential"),
        )
    )

    def forbidden(*a, **kw):
        pytest.fail("builtin child eagerly started an inline MCP transport")

    monkeypatch.setattr(pool_module, "McpClient", forbidden)
    async with child_mcp_scope(deps, persona, team.SubTask("Read a local report")):
        child_owner = deps.mcp_discovery
        assert child_owner is not parent_owner
        assert child_owner.pool is not pool_module._POOL
        assert {row["server"] for row in child_owner.catalog()} == {"opaque", "other"}
        assert {"PARENT_SECRET", "INLINE_SECRET", "INLINE_TOKEN", "INLINE_LITERAL"} <= (
            deps.tool_context.hidden_env
        )
        assert deps.base_registry.get("mcp__opaque__stale_parent") is None
    assert child_owner.closed and not parent_owner.closed
    assert deps.base_registry is original_registry
    assert deps.mcp_discovery is parent_owner


class _Client:
    starts: ClassVar[list[str]] = []
    closes: ClassVar[list[str]] = []
    calls: ClassVar[list[str]] = []
    is_stalled = False
    servers = ()

    def __init__(self, configs, **kwargs):
        self.config = configs[0]

    @property
    def statuses(self):
        return {self.config.name: McpConnectionStatus(server=self.config.name, state="bagli")}

    async def __aenter__(self):
        self.starts.append(self.config.command)
        return self

    async def __aexit__(self, *exc):
        self.closes.append(self.config.command)

    async def register_into(self, registry):
        async def read(args, context):
            self.calls.append(self.config.command)
            return ToolResult(output=self.config.command)

        name = f"mcp__{self.config.name}__read"
        registry.register_or_replace(
            Tool(
                name,
                "Read real configured record",
                {"type": "object", "properties": {}},
                read,
                effect=ToolEffect.REMOTE_READ,
            )
        )
        return (name,)


async def test_selected_inline_tool_uses_private_identity_and_closes_only_child(
    tmp_path, monkeypatch
):
    deps, persona = _inline(tmp_path)
    _Client.starts, _Client.closes, _Client.calls = [], [], []
    monkeypatch.setattr(pool_module, "McpClient", _Client)
    root_pool = McpToolPool()
    monkeypatch.setattr(pool_module, "_POOL", root_pool)
    try:
        await pool_module.ensure_mcp_tools(
            deps.config.mcp_servers,
            ToolRegistry(),
            selected_names=("opaque",),
            refresh_references=False,
            schedule_late=False,
        )
        parent_client = root_pool.connected_client("opaque")
        async with child_mcp_scope(deps, persona, team.SubTask("Read the configured record")):
            assert _Client.starts == ["parent-command"]
            runtime = build_agent_registry(deps, depth=1, run_agent=loop.run_agent)
            owner = deps.mcp_discovery
            discovery = owner.bind(
                runtime,
                permitted=lambda: set(runtime.names()),
                admit=lambda s: True,
                deps=deps,
            )
            result = await discovery.run({"server": "opaque"}, deps.tool_context)
            assert result.ok and "mcp__opaque__read" in result.output
            assert _Client.starts == ["parent-command", "child-command"]
            read = await runtime.execute("mcp__opaque__read", {}, deps.tool_context)
            assert read.output == "child-command"
            assert deps.base_registry.get("mcp__opaque__read") is None
            private_pool = owner.pool
        assert private_pool.is_empty
        assert root_pool.connected_client("opaque") is parent_client
        assert _Client.closes == ["child-command"]
        assert _Client.calls == ["child-command"]
    finally:
        await root_pool.aclose()


async def test_cancelled_inline_scope_drains_selected_private_start(tmp_path, monkeypatch):
    deps, persona = _inline(tmp_path)
    started = asyncio.Event()
    closed = asyncio.Event()

    class Slow(_Client):
        async def __aenter__(self):
            started.set()
            return await super().__aenter__()

        async def register_into(self, registry):
            await asyncio.Event().wait()

        async def __aexit__(self, *exc):
            closed.set()
            await super().__aexit__(*exc)

    monkeypatch.setattr(pool_module, "McpClient", Slow)
    owners = []

    async def child():
        async with child_mcp_scope(deps, persona, team.SubTask("Read configured records")):
            owner = deps.mcp_discovery
            owners.append(owner)
            runtime = ToolRegistry()
            discovery = owner.bind(
                runtime,
                permitted=lambda: set(runtime.names()),
                admit=lambda s: True,
                deps=deps,
            )
            await discovery.run({"server": "opaque"}, deps.tool_context)

    running = asyncio.create_task(child())
    await started.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert owners[0].closed
    assert owners[0].pool.is_empty
    assert closed.is_set()


async def test_explicit_prompt_and_resource_use_only_private_child_catalog(tmp_path, monkeypatch):
    from fusion_cli.mcp_bridge.references import McpCatalog, McpPrompt

    deps, persona = _inline(tmp_path)
    _Client.starts, _Client.closes, _Client.calls = [], [], []

    class References(_Client):
        @property
        def servers(self):
            return (self.config.name,)

        async def catalog(self, server):
            return McpCatalog(prompts=(McpPrompt(server, "inspect"),))

        async def get_prompt(self, server, name, arguments):
            self.calls.append("private prompt")
            return "Inspect the local report"

        async def read_resource(self, server, uri):
            self.calls.append("private resource")
            return "<mcp_kaynak>Untrusted synthetic child resource</mcp_kaynak>"

        def server_instructions(self, server):
            return "Synthetic child usage"

    monkeypatch.setattr(pool_module, "McpClient", References)
    async with child_mcp_scope(deps, persona, team.SubTask("Inspect configured content")):
        owner = deps.mcp_discovery
        runtime = ToolRegistry()
        result = await owner.preflight_selected(
            runtime,
            (),
            permitted=lambda: set(runtime.names()),
            admit=lambda _: True,
            deps=deps,
            task="/mcp__opaque__inspect @opaque:uri://synthetic",
        )
        assert not result.error
        assert result.task == "Inspect the local report"
        assert "Untrusted synthetic child resource" in result.context
        assert "Synthetic child usage" in result.context
        assert References.calls == ["private prompt", "private resource"]
        assert References.starts == ["child-command"]
    assert References.closes == ["child-command"]

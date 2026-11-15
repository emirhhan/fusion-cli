"""Opsiyonel temel defterin ekip ve CLI sınırlarındaki güvenlik sözleşmesi."""

from __future__ import annotations

import io
from dataclasses import replace

import pytest
from rich.console import Console

from fusion_cli.cli import session
from fusion_cli.cli.repl import loop as repl_loop
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.models import HostedConnectorConfig, McpServerConfig
from fusion_cli.core.events import ErrorOccurred
from fusion_cli.core.tools import Tool, ToolContext, ToolResult
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, AgentOutcome
from fusion_cli.engines.agent.team import GENERIC_PERSONA, SubTask
from fusion_cli.engines.agent.team_policy import allowed_tools
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.registry import ToolRegistry
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


def _deps(tmp_path, registry=None):
    return AgentDeps(
        config=make_config(memory_dir=tmp_path / "memory", source=tmp_path / "config.yaml"),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=registry,
    )


def _tool(name, *, mutating=False):
    return Tool(
        name, "Denetim aracı", {}, lambda args, context: ToolResult.success("tamam"), mutating
    )


def test_none_kurucuda_tamamlanir_bos_enjekte_defter_korunur(tmp_path):
    default = _deps(tmp_path)
    empty = ToolRegistry()
    injected = _deps(tmp_path, empty)

    assert default.base_registry is not None
    assert default.base_registry.get("read_file") is not None
    assert injected.base_registry is empty
    assert injected.base_registry.names() == ()


def test_ekip_uzak_ve_salt_okur_suzgecleri_enjekte_defteri_kullanir(tmp_path):
    registry = ToolRegistry()
    registry.register(_tool("read_file"))
    registry.register(_tool("write_file", mutating=True))
    registry.register_or_replace(_tool("github__read"))
    registry.register_or_replace(_tool("jira__write", mutating=True))
    deps = _deps(tmp_path, registry)
    persona = replace(GENERIC_PERSONA, mcp_servers=("github",))

    allowed = allowed_tools(
        deps, persona, SubTask("incele", read_only=True), available=registry.names()
    )

    assert allowed == {"read_file", "github__read"}
    assert deps.base_registry is registry
    assert registry.is_remote("github__read") and registry.is_remote("jira__write")


async def _drive(surface, deps, sink, output, tmp_path):
    async def runner(task, received, **kwargs):
        assert received is deps
        return AgentOutcome(final_text="tamam", messages=[], ok=True)

    if surface == "session":
        return await session._run_agent_with_mcp(
            "incele",
            deps,
            deps.config,
            Publisher(sink),
            history=None,
            mode=ApprovalMode.AUTO,
            extra_system="",
            turn_runner=runner,
        )
    state = ReplState(config=deps.config, memory=null_memory(), root=tmp_path, home=tmp_path / "ev")
    return await repl_loop._drive_agent(
        runner,
        "incele",
        deps,
        state,
        Console(file=output),
        plan_mode=False,
        extra_system="",
        step_limit=None,
    )


@pytest.mark.parametrize("surface", ["session", "repl"])
@pytest.mark.parametrize("transport", ["mcp", "hosted"])
async def test_connector_ayni_enjekte_deftere_eklenir(tmp_path, monkeypatch, surface, transport):
    from fusion_cli.mcp_bridge import pool

    registry = ToolRegistry()
    deps = _deps(tmp_path, registry)
    deps.config = replace(
        deps.config,
        mcp_servers=(McpServerConfig(name="denetim", command="betik"),)
        if transport == "mcp"
        else (),
        hosted_connectors=(
            HostedConnectorConfig("denetim", "https://example.invalid/mcp", "chatgpt_web"),
        )
        if transport == "hosted"
        else (),
    )

    async def ensure(config, target, **kwargs):
        target.register_or_replace(_tool("denetim__read"))
        return ("denetim__read",)

    monkeypatch.setattr(
        pool, "ensure_hosted_tools" if transport == "hosted" else "ensure_mcp_tools", ensure
    )
    sink, output = RecordingSink(), io.StringIO()

    outcome = await _drive(surface, deps, sink, output, tmp_path)

    assert outcome.ok and outcome.final_text == "tamam"
    assert not any(isinstance(event, ErrorOccurred) for event in sink.events)
    assert "bağlanılamadı" not in output.getvalue().lower()
    assert registry.names() == ("denetim__read",)
    assert deps.base_registry is registry

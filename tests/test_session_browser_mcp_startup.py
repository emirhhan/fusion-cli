"""Browser-only turns must not start connectors outside their tool surface."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.appserver import session as session_module
from fusion_cli.appserver.session import AppSession
from fusion_cli.config.models import McpServerConfig
from fusion_cli.core.claude_chrome_names import CLAUDE_CHROME_TOOL_NAMES
from fusion_cli.tools import build_registry


@pytest.mark.parametrize("workspace_mode", ["kod", "sohbet"])
async def test_builtin_browser_turn_skips_mcp_but_next_main_turn_retains_it(
    tmp_path, monkeypatch, workspace_mode
):
    captured = []

    async def execute(task, config, **kwargs):
        captured.append((config, kwargs["allowed_tools"]))
        return SimpleNamespace(ok=True, final_text="done", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    configured = (McpServerConfig(name="fake-connector", command="unused-fake-command"),)
    session._state.config = replace(session._state.config, mcp_servers=configured)
    session._workspace_mode = workspace_mode
    await session._chrome_turn("read https://example.invalid")
    browser_config, allowed = captured[0]
    assert browser_config.mcp_servers == ()
    assert allowed <= set(build_registry().names()) | {"ask_teacher"}
    assert set(CLAUDE_CHROME_TOOL_NAMES) <= allowed
    assert browser_config is not session._state.config
    assert session._state.config.mcp_servers == configured

    await session._run_turn("normal work")
    assert captured[1][0].mcp_servers == configured
    assert session._state.config.mcp_servers == configured


async def test_browser_surface_with_external_tool_keeps_configured_mcp(tmp_path, monkeypatch):
    captured = []

    async def execute(task, config, **kwargs):
        captured.append((config, kwargs["allowed_tools"]))
        return SimpleNamespace(ok=True, final_text="done", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    monkeypatch.setattr(
        session_module,
        "CHROME_CODE_TURN_TOOLS",
        session_module.CHROME_CODE_TURN_TOOLS | {"fake-connector__search"},
    )
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    configured = (McpServerConfig(name="fake-connector", command="unused-fake-command"),)
    session._state.config = replace(session._state.config, mcp_servers=configured)
    await session._chrome_turn("future external-tool surface")
    assert captured[0][0].mcp_servers == configured
    assert "fake-connector__search" in captured[0][1]

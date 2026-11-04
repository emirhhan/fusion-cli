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
        captured.append((config, kwargs["allowed_tools"], kwargs.get("bootstrap_mcp", True)))
        return SimpleNamespace(ok=True, final_text="done", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    configured = (McpServerConfig(name="fake-connector", command="unused-fake-command"),)
    session._state.config = replace(session._state.config, mcp_servers=configured)
    session._workspace_mode = workspace_mode
    await session._chrome_turn("read https://example.invalid")
    browser_config, allowed, bootstrap = captured[0]
    assert browser_config.mcp_servers == configured
    assert bootstrap is False
    assert allowed <= set(build_registry().names()) | {"ask_teacher"}
    assert set(CLAUDE_CHROME_TOOL_NAMES) <= allowed
    assert browser_config is session._state.config
    assert session._state.config.mcp_servers == configured

    await session._run_turn("normal work")
    assert captured[1][0].mcp_servers == configured
    assert captured[1][2] is True
    assert session._state.config.mcp_servers == configured


async def test_browser_surface_with_external_tool_keeps_configured_mcp(tmp_path, monkeypatch):
    captured = []

    async def execute(task, config, **kwargs):
        captured.append((config, kwargs["allowed_tools"], kwargs.get("bootstrap_mcp", True)))
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
    assert captured[0][2] is True


async def test_browser_bootstrap_skip_preserves_shell_secret_caps_and_model_config(
    tmp_path, monkeypatch
):
    from fusion_cli.cli import session as cli_session
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.mcp_bridge import pool, reference_service
    from fusion_cli.tools import shell

    secret_names = ("SYNTHETIC_CONNECTOR_ALPHA", "SYNTHETIC_CONNECTOR_BETA", "SYNTHETIC_BEARER")
    fake_env = dict.fromkeys(secret_names, "synthetic-only")
    fake_env["PUBLIC_SYNTHETIC"] = "visible"
    monkeypatch.setattr(shell, "php_env", lambda: dict(fake_env))
    connections = []
    captured = []

    async def ensure(configs, registry, **kwargs):
        connections.append(tuple(configs))
        return ()

    async def expand(task, configs):
        return SimpleNamespace(task=task, context="", notes=(), warnings=(), error=None)

    async def run(task, deps, **kwargs):
        # Actual run_agent_task already applied runtime settings to this context.
        child_env = shell._shell_env(deps.tool_context)
        assert all(name not in child_env for name in secret_names), (
            "configured secret names escaped"
        )
        assert child_env["PUBLIC_SYNTHETIC"] == "visible"
        assert set(secret_names) <= deps.tool_context.hidden_env
        captured.append((deps.config, kwargs))
        return AgentOutcome(ok=True, final_text="done", messages=[])

    monkeypatch.setattr(pool, "ensure_mcp_tools", ensure)
    monkeypatch.setattr(reference_service, "expand_mcp_references", expand)
    monkeypatch.setattr(cli_session, "new_failure_lines", lambda _: ())
    monkeypatch.setattr(cli_session, "run_agent", run)
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    configured = (
        McpServerConfig(
            name="fake-connector",
            command="unused-fake-command",
            env_names=secret_names[:2],
            token_env=secret_names[2],
        ),
    )
    original = replace(session._state.config, mcp_servers=configured)
    session._state.config = original
    await session._chrome_turn("browser code task")
    assert captured[0][0] is original
    assert "run_shell" in captured[0][1]["allowed_tools"]
    assert set(CLAUDE_CHROME_TOOL_NAMES) <= captured[0][1]["allowed_tools"]
    assert not connections, "builtin browser surface must not bootstrap a connector"

    await session._run_turn("normal main task")
    assert captured[1][0].mcp_servers == configured
    assert connections == [configured]
    monkeypatch.setattr(
        session_module,
        "CHROME_CODE_TURN_TOOLS",
        session_module.CHROME_CODE_TURN_TOOLS | {"fake-connector__search"},
    )
    await session._chrome_turn("external future surface")
    assert connections == [configured, configured]
    assert all(config.mcp_servers == configured for config, _ in captured)

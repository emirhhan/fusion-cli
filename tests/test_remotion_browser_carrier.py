"""Host browser değerinin araca taşınması ve mevcut alias uyumu."""

from fusion_cli.core.remotion_browser import RemotionBrowser

from .fakes import make_config


def test_existing_browser_alias_is_same_pure_core_value():
    from fusion_cli.tools.remotion_observe import ExistingBrowser

    assert ExistingBrowser is RemotionBrowser


async def test_host_browser_reaches_existing_tool_context_without_json(monkeypatch, tmp_path):
    from fusion_cli.cli import session
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import AgentOutcome

    context = ToolContext(root=tmp_path)
    browser = RemotionBrowser(tmp_path / "chrome", "chrome-for-testing")

    async def run(task, deps, **kwargs):
        assert deps.tool_context.changes is context.changes
        assert deps.tool_context.remotion_contract is context.remotion_contract
        assert deps.tool_context.remotion_browser is browser
        assert deps.verifier is not None
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr(session, "run_agent", run)
    await session.run_agent_task(
        "Generic",
        make_config(
            memory_dir=tmp_path / "memory", source=tmp_path / "config.yaml", mcp_servers=()
        ),
        sinks=(),
        prompter_factory=lambda drain: None,
        tool_context=context,
        interactive=False,
        remotion_browser=browser,
    )


def test_app_host_browser_carrier_defaults_none_and_does_not_create_state(tmp_path):
    from fusion_cli.cli.app_host import AppHostDependencies
    from fusion_cli.core.tools import ToolContext

    assert AppHostDependencies().remotion_browser is None
    assert ToolContext(root=tmp_path).remotion_browser is None


async def test_app_actual_turn_forwards_browser_carrier(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from fusion_cli.appserver import session
    from fusion_cli.cli import session as cli_session
    from fusion_cli.memory.factory import null_memory

    browser = RemotionBrowser(tmp_path / "chrome", "chrome-for-testing")
    captured = []

    async def run(task, config, **kwargs):
        captured.append(kwargs.get("remotion_browser"))
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    config = make_config(memory_dir=tmp_path / "memory", source=tmp_path / "config.yaml")
    monkeypatch.setattr(session, "load_config", lambda: config)
    monkeypatch.setattr(session, "build_memory", lambda *args, **kwargs: null_memory())
    monkeypatch.setattr(session, "FernetSecretStore", Mock())
    monkeypatch.setattr(session, "secret_key", lambda: b"test")
    monkeypatch.setattr(cli_session, "run_agent_task", run)
    app = session.AppSession(
        lambda line: None, root=tmp_path, home=tmp_path / "home", remotion_browser=browser
    )
    await app._chrome_turn("Generic")
    assert captured == [browser]


async def test_tui_actual_turn_forwards_browser_carrier(monkeypatch, tmp_path):
    from fusion_cli.cli.repl import tui_loop
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.engines.agent import AgentOutcome
    from fusion_cli.memory.factory import null_memory

    browser = RemotionBrowser(tmp_path / "chrome", "chrome-for-testing")
    captured = []

    async def run(task, config, **kwargs):
        captured.append(kwargs.get("remotion_browser"))
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr(tui_loop, "run_agent_task", run)
    state = ReplState(
        make_config(), null_memory(), tmp_path, tmp_path / "home", remotion_browser=browser
    )
    await tui_loop._TuiSession(state)._turn("Generic")
    assert captured == [browser]

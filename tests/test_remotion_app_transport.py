"""Uygulama ve TUI gerçek tur çağrılarının host taşımasını koruması."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fusion_cli.engines.agent import AgentOutcome
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.mark.parametrize("selected", [False, True])
async def test_app_execute_turn_forwards_constructor_host_transport(
    monkeypatch, tmp_path, selected
):
    from fusion_cli.appserver import session
    from fusion_cli.cli import session as cli_session

    async def transport(request):
        raise AssertionError("Generic tur render başlatmamalı")

    captured = []

    async def run(task, config, **kwargs):
        captured.append(kwargs.get("remotion_transport"))
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    config = make_config(
        memory_dir=tmp_path / "memory", source=tmp_path / "config.yaml", mcp_servers=()
    )
    monkeypatch.setattr(session, "load_config", lambda: config)
    monkeypatch.setattr(session, "build_memory", lambda *args, **kwargs: null_memory())
    monkeypatch.setattr(session, "FernetSecretStore", Mock())
    monkeypatch.setattr(session, "secret_key", lambda: b"test")
    monkeypatch.setattr(cli_session, "run_agent_task", run)
    options = {"remotion_transport": transport} if selected else {}
    app = session.AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home", **options)
    await app._chrome_turn("Generic")
    assert captured == [transport if selected else None]


@pytest.mark.parametrize("selected", [False, True])
async def test_tui_actual_turn_forwards_state_host_transport(monkeypatch, tmp_path, selected):
    from fusion_cli.cli.repl import tui_loop
    from fusion_cli.cli.repl.state import ReplState

    async def transport(request):
        raise AssertionError("Generic tur render başlatmamalı")

    captured = []

    async def run(task, config, **kwargs):
        captured.append(kwargs.get("remotion_transport"))
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr(tui_loop, "run_agent_task", run)
    state = ReplState(
        make_config(),
        null_memory(),
        tmp_path,
        tmp_path / "home",
        remotion_transport=transport if selected else None,
    )
    await tui_loop._TuiSession(state)._turn("Generic")
    assert captured == [transport if selected else None]

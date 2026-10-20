"""Açık host kit gereksinimi model/RPC verisine güvenmeden gerçek tura gider."""

import importlib
import sys
from unittest.mock import Mock

import pytest

from fusion_cli.cli.app_host import AppHostDependencies
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.mark.parametrize("required", [False, True])
def test_native_main_passes_only_explicit_host_requirement(monkeypatch, required):
    cli = importlib.import_module("fusion_cli.cli.app")
    from fusion_cli.appserver import server

    captured = []

    async def run_stdio(root, home, **kwargs):
        captured.append(kwargs.get("require_remotion_kit", False))

    monkeypatch.setattr(server, "run_stdio", run_stdio)
    monkeypatch.setattr("fusion_cli.accounts.remembered_account", lambda: None)
    monkeypatch.setattr(sys, "argv", ["fusion", "app"])
    with pytest.raises(SystemExit):
        cli.main(host_dependencies=AppHostDependencies(require_remotion_kit=required))
    assert captured == [required]


@pytest.mark.parametrize("required", [False, True])
async def test_stdio_requirement_reaches_actual_session_constructor(
    monkeypatch, tmp_path, required
):
    from fusion_cli.appserver import server

    captured = []

    class Session:
        def __init__(self, writer, *, root, home, **kwargs):
            captured.append(kwargs.get("require_remotion_kit", False))

        async def close(self):
            pass

    async def lines():
        if False:
            yield ""

    monkeypatch.setattr(server, "AppSession", Session)
    monkeypatch.setattr(server, "force_utf8_stdio", lambda: None)
    monkeypatch.setattr(server, "_stdin_lines", lines)
    await server.run_stdio(tmp_path, tmp_path, require_remotion_kit=required)
    assert captured == [required]


@pytest.mark.parametrize("required", [False, True])
async def test_native_actual_turn_preserves_host_requirement(monkeypatch, tmp_path, required):
    from fusion_cli.appserver import session
    from fusion_cli.cli import session as cli_session

    captured = []

    from fusion_cli.engines.agent import AgentOutcome

    async def run(task, deps, **kwargs):
        captured.append(deps.tool_context.remotion_contract.is_required)
        return AgentOutcome("bitti", [], 0, ok=True)

    config = make_config(memory_dir=tmp_path / "memory", source=tmp_path / "config.yaml")
    monkeypatch.setattr(session, "load_config", lambda: config)
    monkeypatch.setattr(session, "build_memory", lambda *args, **kwargs: null_memory())
    monkeypatch.setattr(session, "FernetSecretStore", Mock())
    monkeypatch.setattr(session, "secret_key", lambda: b"test")
    monkeypatch.setattr(cli_session, "run_agent", run)
    app = session.AppSession(
        lambda line: None, root=tmp_path, home=tmp_path / "home", require_remotion_kit=required
    )
    await app._chrome_turn("Generic")
    assert captured == [required]

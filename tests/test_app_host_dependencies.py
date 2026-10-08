"""Trusted host bağımlılığının CLI bağlamından gerçek oturuma taşınması."""

import sys

import pytest

from fusion_cli.cli.app_host import AppHostDependencies


@pytest.mark.parametrize("selected", [False, True])
def test_main_typer_app_protocol_forwards_typed_host(monkeypatch, selected):
    import importlib

    cli = importlib.import_module("fusion_cli.cli.app")
    from fusion_cli.appserver import server

    captured = []

    async def transport(request):
        raise AssertionError("Bootstrap render başlatmamalı")

    async def run_stdio(root, home, **kwargs):
        captured.append(kwargs.get("remotion_transport"))

    monkeypatch.setattr(server, "run_stdio", run_stdio)
    monkeypatch.setattr("fusion_cli.accounts.remembered_account", lambda: None)
    monkeypatch.setattr(sys, "argv", ["fusion", "app"])
    with pytest.raises(SystemExit) as exit:
        if selected:
            cli.main(host_dependencies=AppHostDependencies(transport))
        else:
            cli.main()
    assert exit.value.code == 0
    assert captured == [transport if selected else None]


@pytest.mark.parametrize("selected", [False, True])
async def test_stdio_serve_passes_host_to_actual_session_constructor(
    monkeypatch, tmp_path, selected
):
    from fusion_cli.appserver import server

    captured = []

    async def transport(request):
        raise AssertionError("Bootstrap render başlatmamalı")

    class Session:
        def __init__(self, writer, *, root, home, **kwargs):
            captured.append(kwargs.get("remotion_transport"))

        async def close(self):
            pass

    async def lines():
        if False:
            yield ""

    monkeypatch.setattr(server, "AppSession", Session)
    monkeypatch.setattr(server, "force_utf8_stdio", lambda: None)
    monkeypatch.setattr(server, "_stdin_lines", lines)
    await server.run_stdio(tmp_path, tmp_path, remotion_transport=transport if selected else None)
    assert captured == [transport if selected else None]

"""REPL `/mcp` paneli birebir (#250, #251)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fusion_cli.cli.repl import mcp_panel
from fusion_cli.config import loader, trust
from fusion_cli.config.mcp_json import write_project_mcp_servers
from fusion_cli.config.models import McpScope, McpServerConfig


@pytest.fixture
def izole(tmp_path, monkeypatch):
    kok = tmp_path / "proje"
    kok.mkdir()
    monkeypatch.chdir(kok)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    kullanici = tmp_path / "xdg" / "fusion-cli" / "config.yaml"
    monkeypatch.setattr(loader, "user_config_candidates", lambda: (kullanici,))
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "guven.json")
    return kok


def test_repl_remove_proje_sunucusunu_mcp_json_dan_gercekten_siler(izole):
    write_project_mcp_servers(
        izole, (McpServerConfig(name="team", command="npx", scope=McpScope.PROJECT),)
    )
    state = SimpleNamespace(config=loader.load_config())
    assert [s.name for s in state.config.mcp_servers] == ["team"]
    cevap = mcp_panel.handle(state, "remove", "team")
    assert "kaldırıldı" in cevap
    assert json.loads((izole / ".mcp.json").read_text())["mcpServers"] == {}
    assert state.config.mcp_servers == ()


def test_panel_durum_ve_ac_kapa(izole):
    write_project_mcp_servers(
        izole, (McpServerConfig(name="team", command="npx", scope=McpScope.PROJECT),)
    )
    state = SimpleNamespace(config=loader.load_config())
    assert "team [proje · stdio] npx" in mcp_panel.panel(state.config.mcp_servers, izole)
    mcp_panel.handle(state, "disable", "team")
    assert state.config.mcp_servers == ()
    assert "team ○ Kapalı" in mcp_panel.panel(state.config.mcp_servers, izole)
    mcp_panel.handle(state, "enable", "team")
    assert [s.name for s in state.config.mcp_servers] == ["team"]


def test_clear_auth_yalniz_uzak_sunucuda(izole):
    state = SimpleNamespace(config=SimpleNamespace(mcp_servers=(McpServerConfig("s", "c"),)))
    assert "uzak" in mcp_panel.handle(state, "clear-auth", "s")
    assert mcp_panel.handle(state, "bilinmeyen", "") is None

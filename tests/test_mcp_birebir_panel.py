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


class _SahteIstemci:
    def registered_tool_names(self, server):
        return ("github__create_issue", "github__get_issue")


def test_panel_bagli_sunucuda_arac_sayisini_gosterir(izole, monkeypatch):
    from fusion_cli.mcp_bridge import pool
    from fusion_cli.mcp_bridge.types import McpConnectionStatus

    monkeypatch.setattr(
        pool,
        "mcp_pool_statuses",
        lambda: {"team": McpConnectionStatus("team", "bagli", tool_count=5)},
    )
    server = McpServerConfig(name="team", command="npx", scope=McpScope.PROJECT)
    assert "✔ Bağlandı · 5 araç" in mcp_panel.panel((server,), izole)


def test_mcp_tools_tam_ad_ve_izin_durumu(izole, monkeypatch):
    from fusion_cli.config.permission_rules import (
        PermissionDecision,
        PermissionRuleSet,
        parse_rule,
    )
    from fusion_cli.mcp_bridge import pool

    monkeypatch.setattr(pool, "connected_mcp_client", lambda name: _SahteIstemci())
    rules = PermissionRuleSet(
        (
            parse_rule("mcp__github__get_*", PermissionDecision.ALLOW),
            parse_rule("mcp__github__create_issue", PermissionDecision.DENY),
        )
    )
    state = SimpleNamespace(
        config=SimpleNamespace(mcp_servers=(McpServerConfig("github", "npx"),)),
        root=izole,
        permission_rules=lambda: rules,
    )
    cevap = mcp_panel.handle(state, "tools", "github")
    assert "mcp__github__create_issue — reddedildi" in cevap
    assert "mcp__github__get_issue — izinli" in cevap


def test_mcp_tools_bagli_olmayan_sunucu(izole, monkeypatch):
    from fusion_cli.mcp_bridge import pool

    monkeypatch.setattr(pool, "connected_mcp_client", lambda name: None)
    state = SimpleNamespace(
        config=SimpleNamespace(mcp_servers=(McpServerConfig("github", "npx"),)), root=izole
    )
    assert "henüz bağlanmadı" in mcp_panel.handle(state, "tools", "github")
    assert "Kullanım" in mcp_panel.handle(state, "tools", "")

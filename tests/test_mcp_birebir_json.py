"""Claude Code `.mcp.json` biçimi ve kapsamları birebir (#234, #236, #238, #270)."""

from __future__ import annotations

import json

import pytest

from fusion_cli.config import loader, trust
from fusion_cli.config.mcp_entry import McpEntryError, parse_entry, to_entry
from fusion_cli.config.mcp_json import (
    merge_mcp_servers,
    read_project_mcp_report,
    read_project_mcp_servers,
)
from fusion_cli.config.mcp_local import (
    read_local_mcp_servers,
    remove_local_mcp_server,
    upsert_local_mcp_server,
)
from fusion_cli.config.models import McpScope, McpServerConfig, McpTransport


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


def test_belgedeki_butun_alanlar_kabul_edilir_ve_uygulanir():
    server = parse_entry(
        "api",
        {
            "type": "http",
            "url": "https://api.example.com/mcp",
            "headers": {"Authorization": "Bearer ${API_KEY}"},
            "headersHelper": "/opt/bin/get-headers.sh",
            "timeout": 600000,
            "alwaysLoad": True,
            "oauth": {
                "clientId": "abc",
                "callbackPort": 8080,
                "authServerMetadataUrl": "https://auth.example.com/.well-known/openid",
                "scopes": "channels:read chat:write",
            },
        },
        scope=McpScope.PROJECT,
    )
    assert server.headers == (("Authorization", "Bearer ${API_KEY}"),)
    assert server.headers_helper == "/opt/bin/get-headers.sh"
    assert server.timeout_ms == 600000
    assert server.always_load is True
    assert server.client_id == "abc"
    assert server.oauth_callback_port == 8080
    assert server.scopes == ("channels:read", "chat:write")
    # Gidiş-dönüş: yazılan girdi Claude biçimini korur.
    assert to_entry(server)["oauth"] == {
        "clientId": "abc",
        "callbackPort": 8080,
        "authServerMetadataUrl": "https://auth.example.com/.well-known/openid",
        "scopes": "channels:read chat:write",
    }


def test_timeout_1000_altinda_yok_sayilir_ve_metadata_https_olmali():
    assert parse_entry("x", {"command": "c", "timeout": 500}, scope=McpScope.USER).timeout_ms is None
    with pytest.raises(McpEntryError, match="https"):
        parse_entry(
            "x",
            {"type": "http", "url": "https://a", "oauth": {"authServerMetadataUrl": "http://a"}},
            scope=McpScope.USER,
        )


def test_typesiz_url_stdio_sayilir_ve_girdi_atlanir():
    with pytest.raises(McpEntryError, match='"type"'):
        parse_entry("x", {"url": "https://a/mcp"}, scope=McpScope.PROJECT)


def test_tek_hatali_girdi_digerlerini_dusurmez(izole):
    (izole / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "iyi": {"command": "npx"},
                    "urlsuz": {"url": "https://a/mcp"},
                    "sdk": {"type": "sdk"},
                    "bozuk": {"type": "gopher", "url": "x"},
                }
            }
        ),
        encoding="utf-8",
    )
    servers, problems = read_project_mcp_report(izole)
    assert [server.name for server in servers] == ["iyi"]
    assert len(problems) == 3
    assert any("sdk" in problem for problem in problems)
    assert [server.name for server in read_project_mcp_servers(izole)] == ["iyi"]


def test_guvenilen_projede_hatali_girdi_fusion_acilisini_engellemez(izole):
    (izole / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"iyi": {"command": "npx"}, "kotu": {"url": "https://a"}}}),
        encoding="utf-8",
    )
    trust.approve_file(izole, izole / ".mcp.json")
    config = loader.load_config()
    assert [server.name for server in config.mcp_servers if server.scope is McpScope.PROJECT] == [
        "iyi"
    ]


def test_yerel_kapsam_yalniz_kendi_projesinde_yuklenir(izole, tmp_path):
    server = McpServerConfig(
        name="stripe",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.stripe.com",
        scope=McpScope.LOCAL,
    )
    upsert_local_mcp_server(izole, server)
    (loaded,) = read_local_mcp_servers(izole)
    assert loaded.scope is McpScope.LOCAL
    assert loaded.url == "https://mcp.stripe.com"
    baska = tmp_path / "baska"
    baska.mkdir()
    assert read_local_mcp_servers(baska) == ()
    remove_local_mcp_server(izole, "stripe")
    assert read_local_mcp_servers(izole) == ()


def test_oncelik_local_project_user_alanlar_birlestirilmez():
    user = McpServerConfig(name="a", command="u", scope=McpScope.USER)
    project = McpServerConfig(name="a", command="p", scope=McpScope.PROJECT)
    local = McpServerConfig(name="a", command="l", scope=McpScope.LOCAL)
    (winner,) = merge_mcp_servers((user,), (project,), (local,))
    assert winner.command == "l"
    (winner,) = merge_mcp_servers((user,), (project,))
    assert winner.command == "p"

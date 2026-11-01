"""Kuruluş MCP denetimi Claude Code gibi (#274; code.claude.com/docs/en/managed-mcp)."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.config.mcp_policy import (
    McpPolicy,
    add_refusal,
    filter_servers,
    load_policy,
    url_matches,
)
from fusion_cli.config.models import McpServerConfig, McpTransport


def _http(name: str, url: str) -> McpServerConfig:
    return McpServerConfig(name=name, transport=McpTransport.STREAMABLE_HTTP, url=url)


def _stdio(name: str, *argv: str) -> McpServerConfig:
    return McpServerConfig(name=name, command=argv[0], args=tuple(argv[1:]))


def _names(servers) -> list[str]:
    return [item.name for item in servers]


def test_url_kaliplari_belgedeki_tablo():
    assert url_matches("https://mcp.example.com/*", "https://MCP.example.com./api")
    assert not url_matches("https://mcp.example.com/*", "https://mcp.example.com:8443/api")
    assert url_matches("https://mcp.example.com", "https://mcp.example.com/x/y")
    assert url_matches("https://mcp.example.com:*/*", "https://mcp.example.com:8443/a")
    assert url_matches("https://*.example.com/*", "https://a.example.com:9000/a")
    assert url_matches("http://localhost:*/*", "http://localhost:3000/mcp")
    assert url_matches("*://mcp.example.com/*", "http://mcp.example.com/a")
    assert not url_matches("*://mcp.example.com/*", "http://mcp.example.com:8080/a")
    assert not url_matches("https://mcp.example.com/API/*", "https://mcp.example.com/api/x")


def test_ret_her_seyi_gecer_izin_turune_gore():
    servers = (
        _http("gh", "https://api.githubcopilot.com/mcp"),
        _http("dis", "https://external.example.com/mcp"),
        _stdio("fs", "npx", "-y", "server-fs"),
        _stdio("tehlikeli", "npx", "-y", "server-fs"),
    )
    policy = McpPolicy(
        allowed=({"serverUrl": "https://api.githubcopilot.com/*"},),
        denied=({"serverName": "tehlikeli"},),
    )

    # Uzak: URL listesi var, eşleşen geçer. Stdio: komut/ad girdisi yok → engellenir.
    assert _names(filter_servers(servers, policy, {})) == ["gh"]
    name_only = McpPolicy(allowed=({"serverName": "fs"}, {"serverName": "gh"}))
    assert _names(filter_servers(servers, name_only, {})) == ["gh", "fs"]
    assert filter_servers(servers, McpPolicy(allowed=()), {}) == ()
    assert len(filter_servers(servers, McpPolicy(), {})) == 4


def test_komut_eslesmesi_birebir_ve_degisken_acilir():
    policy = McpPolicy(allowed=({"serverCommand": ["${HOME}/bin/s", "-v"]},))
    ok = _stdio("a", "/ev/bin/s", "-v")
    extra = _stdio("b", "/ev/bin/s", "-v", "--x")

    assert _names(filter_servers((ok, extra), policy, {"HOME": "/ev"})) == ["a"]


def test_managed_mcp_json_tekel_ve_saglanan_sunucular(tmp_path: Path):
    managed = tmp_path / "yonetim"
    managed.mkdir()
    (managed / "managed-mcp.json").write_text(
        json.dumps({"mcpServers": {"sirket": {"type": "http", "url": "https://s.example.com"}}}),
        encoding="utf-8",
    )
    (managed / "managed-settings.json").write_text(
        json.dumps(
            {
                "managedMcpServers": {
                    "ara": {"type": "http", "url": "https://ara.example.com/mcp"},
                    "kotu": {"type": "stdio", "command": "rm"},
                    "duz": {"type": "http", "url": "http://x.example.com"},
                },
                "allowedMcpServers": [],
            }
        ),
        encoding="utf-8",
    )
    policy = load_policy(tmp_path, home=tmp_path / "ev", directory=managed)
    user = (_http("benim", "https://b.example.com"),)

    # Tekel: kullanıcı sunucusu düşer; kuruluşunkiler izin listesi ([]) olmadan da yüklenir.
    assert _names(filter_servers(user, policy, {})) == ["sirket", "ara"]
    assert "exclusive control" in add_refusal(user[0], tmp_path, policy=policy)


def test_kullanici_ret_listesi_birlesir_izin_kilidi(tmp_path: Path):
    managed = tmp_path / "yonetim"
    managed.mkdir()
    (managed / "managed-settings.json").write_text(
        json.dumps(
            {
                "allowManagedMcpServersOnly": True,
                "allowedMcpServers": [{"serverName": "a"}],
            }
        ),
        encoding="utf-8",
    )
    claude = tmp_path / "ev" / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.json").write_text(
        json.dumps(
            {"allowedMcpServers": [{"serverName": "b"}], "deniedMcpServers": [{"serverName": "a"}]}
        ),
        encoding="utf-8",
    )
    policy = load_policy(tmp_path, home=tmp_path / "ev", directory=managed)
    servers = (_stdio("a", "x"), _stdio("b", "y"))

    assert filter_servers(servers, policy, {}) == ()
    assert "explicitly blocked" in add_refusal(servers[0], tmp_path, policy=policy)
    assert "not allowed" in add_refusal(servers[1], tmp_path, policy=policy)


def test_politika_yoksa_yapilandirma_aynen(tmp_path: Path):
    policy = load_policy(tmp_path, home=tmp_path / "ev", directory=tmp_path / "yok")

    assert policy.is_empty


def test_load_config_ret_listesini_uygular(tmp_path: Path, monkeypatch):
    from fusion_cli.config import mcp_policy
    from fusion_cli.config.loader import load_config

    managed = tmp_path / "yonetim"
    managed.mkdir()
    (managed / "managed-settings.json").write_text(
        json.dumps({"deniedMcpServers": [{"serverName": "yasak"}]}), encoding="utf-8"
    )
    monkeypatch.setattr(mcp_policy, "managed_dir", lambda: managed)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "mcp_servers:\n  - name: yasak\n    command: npx\n  - name: serbest\n    command: npx\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert _names(load_config(config_file).mcp_servers) == ["serbest"]


# --- Kalan alt yüzeyler (#274): --mcp-config çıkışı, mcp remove iletisi ----------------------


def test_managed_mcp_json_varken_mcp_config_acilista_reddedilir(tmp_path: Path):
    from fusion_cli.config.mcp_policy import DYNAMIC_CONFIG_REFUSAL, mcp_config_refusal

    managed = tmp_path / "yonetim"
    managed.mkdir()
    assert mcp_config_refusal(tmp_path, directory=managed) is None
    (managed / "managed-mcp.json").write_text(json.dumps({"mcpServers": {}}))

    assert mcp_config_refusal(tmp_path, directory=managed) == DYNAMIC_CONFIG_REFUSAL
    assert "enterprise MCP config is present" in DYNAMIC_CONFIG_REFUSAL


def test_cli_mcp_config_ve_managed_mcp_json_birlikte_cikis_verir(tmp_path: Path, monkeypatch):
    from typer.testing import CliRunner

    from fusion_cli.cli.app import app
    from fusion_cli.config import mcp_cli, mcp_policy

    managed = tmp_path / "yonetim"
    managed.mkdir()
    (managed / "managed-mcp.json").write_text(json.dumps({"mcpServers": {}}))
    monkeypatch.setattr(mcp_policy, "managed_dir", lambda: managed)
    for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    monkeypatch.setattr(mcp_cli, "_STATE", [mcp_cli._STATE[0]])  # oturum bayrağı sızmasın
    monkeypatch.chdir(tmp_path)
    config = json.dumps({"mcpServers": {"x": {"type": "http", "url": "https://x.example/mcp"}}})

    result = CliRunner().invoke(app, ["--mcp-config", config, "mcp", "list"])

    assert result.exit_code == 1
    assert "enterprise MCP config is present" in result.output


def test_kurulusun_sagladigi_sunucu_kaldirilamaz(tmp_path: Path):
    from fusion_cli.config.mcp_policy import remove_refusal

    policy = McpPolicy(provided=(_http("kurum", "https://mcp.kurum.example"),))

    mesaj = remove_refusal(_http("kurum", "https://mcp.kurum.example"), tmp_path, policy=policy)

    assert mesaj is not None and "provided by your organization" in mesaj
    assert remove_refusal(_http("benim", "https://x.example"), tmp_path, policy=policy) is None


def test_mcp_remove_kurulus_sunucusunda_iletiyle_reddeder(tmp_path: Path, monkeypatch):
    import pytest

    from fusion_cli.cli.mcp_manage import remove_named
    from fusion_cli.config import mcp_policy
    from fusion_cli.core.errors import ConfigError

    from .fakes import make_config

    managed = tmp_path / "yonetim"
    managed.mkdir()
    settings = {
        "managedMcpServers": {"kurum": {"type": "http", "url": "https://mcp.kurum.example"}}
    }
    (managed / "managed-settings.json").write_text(json.dumps(settings))
    monkeypatch.setattr(mcp_policy, "managed_dir", lambda: managed)
    monkeypatch.setenv("HOME", str(tmp_path / "ev"))
    config = make_config(mcp_servers=(_http("kurum", "https://mcp.kurum.example"),))

    with pytest.raises(ConfigError, match="provided by your organization"):
        remove_named(config, tmp_path, "kurum", None)

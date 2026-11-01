"""Kuruluş MCP'si kalan yüzeyler (#274): `managed` kapsamı, /mcp 'Managed MCPs' grubu,
allowAllClaudeAiMcps (barındırmalı connector'lar), politikanın kullanıcı verisini silmemesi.

Belge: code.claude.com/docs/en/managed-mcp.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from fusion_cli.config import mcp_policy
from fusion_cli.config.mcp_policy import filter_hosted_connectors, load_policy
from fusion_cli.config.models import HostedConnectorConfig, McpScope


def _managed(tmp_path: Path, *, settings: dict | None = None, exclusive: dict | None = None):
    directory = tmp_path / "yonetim"
    directory.mkdir(exist_ok=True)
    if settings is not None:
        (directory / "managed-settings.json").write_text(json.dumps(settings), encoding="utf-8")
    if exclusive is not None:
        (directory / "managed-mcp.json").write_text(json.dumps(exclusive), encoding="utf-8")
    return directory


def _connector(name: str, url: str) -> HostedConnectorConfig:
    return HostedConnectorConfig(name=name, url=url, provider="claude_web", verified=True)


@pytest.fixture
def ev(tmp_path, monkeypatch):
    for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    kok = tmp_path / "proje"
    kok.mkdir()
    monkeypatch.chdir(kok)
    return tmp_path


def test_kurulus_sunuculari_managed_kapsaminda(tmp_path: Path):
    directory = _managed(
        tmp_path,
        settings={"managedMcpServers": {"ara": {"type": "http", "url": "https://a.example"}}},
        exclusive={"mcpServers": {"sirket": {"command": "npx"}}},
    )
    policy = load_policy(tmp_path, home=tmp_path / "ev", directory=directory)

    assert policy.exclusive is not None
    assert {item.scope for item in (*policy.exclusive, *policy.provided)} == {McpScope.MANAGED}


def test_managed_kapsam_add_ile_secilemez():
    import typer

    from fusion_cli.cli.mcp_commands import _parse_scope

    with pytest.raises(typer.BadParameter):
        _parse_scope("managed")


def test_politika_yazmada_kullanici_kaydini_silmez_kurulus_kaydini_yazmaz(ev, monkeypatch):
    from fusion_cli.config.loader import load_config
    from fusion_cli.config.writer import write_mcp_servers

    directory = _managed(
        ev,
        settings={
            "deniedMcpServers": [{"serverName": "yasak"}],
            "managedMcpServers": {"kurum": {"type": "http", "url": "https://k.example/mcp"}},
        },
    )
    monkeypatch.setattr(mcp_policy, "managed_dir", lambda: directory)
    config_file = ev / "config.yaml"
    config_file.write_text(
        "mcp_servers:\n"
        "  - name: yasak\n    command: npx\n"
        "  - name: kurum\n    command: benim-kurum\n"
        "  - name: serbest\n    command: npx\n",
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert sorted(s.name for s in config.mcp_servers) == ["kurum", "serbest"]

    write_mcp_servers(config, config_file)

    written = yaml.safe_load(config_file.read_text(encoding="utf-8"))["mcp_servers"]
    by_name = {entry["name"]: entry for entry in written}
    # Ret listesindeki ve kuruluş adıyla gölgelenen kullanıcı kaydı korunur; kuruluşun
    # sunucusu kullanıcının config.yaml'ına sızmaz.
    assert sorted(by_name) == ["kurum", "serbest", "yasak"]
    assert by_name["kurum"]["command"] == "benim-kurum"
    assert "url" not in by_name["kurum"]


def test_tekel_varken_barindirmali_connectorlar_dusurulur(tmp_path: Path):
    directory = _managed(tmp_path, exclusive={"mcpServers": {}})
    policy = load_policy(tmp_path, home=tmp_path / "ev", directory=directory)
    connectors = (_connector("meta", "https://mcp.facebook.com/ads"),)

    assert filter_hosted_connectors(connectors, policy, {}) == ()


def test_allow_all_claude_ai_mcps_yalniz_yonetilen_ayardan(tmp_path: Path):
    claude = tmp_path / "ev" / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.json").write_text(json.dumps({"allowAllClaudeAiMcps": True}))
    directory = _managed(tmp_path, exclusive={"mcpServers": {}})
    connectors = (
        _connector("meta", "https://mcp.facebook.com/ads"),
        _connector("yasak", "https://bad.example/mcp"),
    )

    user_only = load_policy(tmp_path, home=tmp_path / "ev", directory=directory)
    assert filter_hosted_connectors(connectors, user_only, {}) == ()

    _managed(
        tmp_path,
        settings={"allowAllClaudeAiMcps": True, "deniedMcpServers": [{"serverName": "yasak"}]},
    )
    managed = load_policy(tmp_path, home=tmp_path / "ev", directory=directory)
    kept = filter_hosted_connectors(connectors, managed, {})
    assert [item.name for item in kept] == ["meta"]


def test_ret_ve_izin_listesi_connectorlara_uygulanir(tmp_path: Path):
    directory = _managed(
        tmp_path, settings={"allowedMcpServers": [{"serverUrl": "https://mcp.facebook.com/*"}]}
    )
    policy = load_policy(tmp_path, home=tmp_path / "ev", directory=directory)
    connectors = (
        _connector("meta", "https://mcp.facebook.com/ads"),
        _connector("diger", "https://other.example/mcp"),
    )

    assert [item.name for item in filter_hosted_connectors(connectors, policy, {})] == ["meta"]
    empty = load_policy(tmp_path, home=tmp_path / "ev", directory=tmp_path / "yok")
    assert filter_hosted_connectors(connectors, empty, {}) == connectors


def test_ensure_hosted_tools_politikayi_uygular(tmp_path: Path, monkeypatch):
    from fusion_cli.mcp_bridge import pool

    from .fakes import make_config

    directory = _managed(tmp_path, exclusive={"mcpServers": {}})
    monkeypatch.setattr(mcp_policy, "managed_dir", lambda: directory)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pool, "_hosted_channel", lambda _config: pytest.fail("oturuma gidilmemeli"))
    config = make_config(hosted_connectors=(_connector("meta", "https://mcp.facebook.com/ads"),))

    assert asyncio.run(pool.ensure_hosted_tools(config, object())) == ()


def test_repl_paneli_managed_mcps_grubu(ev, monkeypatch):
    from fusion_cli.cli.repl import mcp_panel
    from fusion_cli.config.models import McpServerConfig, McpTransport

    servers = (
        McpServerConfig(name="benim", command="npx"),
        McpServerConfig(
            name="kurum",
            transport=McpTransport.STREAMABLE_HTTP,
            url="https://k.example/mcp",
            scope=McpScope.MANAGED,
        ),
    )

    text = mcp_panel.panel(servers, ev / "proje")

    assert "Managed MCPs" in text
    assert "User MCPs" in text
    assert text.index("User MCPs") < text.index("benim") < text.index("Managed MCPs")
    assert text.index("Managed MCPs") < text.index("kurum [yönetilen · streamable_http]")


def test_masaustu_kurulus_sunucusunu_kaldirmaz_guven_yazmaz(tmp_path: Path):
    from fusion_cli.appserver.connectors import remove_connector, review_connector
    from fusion_cli.config.models import McpServerConfig, McpTransport

    from .fakes import make_config

    server = McpServerConfig(
        name="kurum",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://k.example/mcp",
        scope=McpScope.MANAGED,
    )
    config = make_config(mcp_servers=(server,))

    updated, reply = remove_connector(config, {"ad": "kurum"}, root=tmp_path)
    assert updated is None and "provided by your organization" in reply["metin"]
    updated, reply = review_connector(config, {"ad": "kurum", "guven": "trusted"})
    assert updated is None and not reply["ok"]

"""`--mcp-config` / `--strict-mcp-config` (#253)."""

from __future__ import annotations

import json

import pytest

from fusion_cli.config import loader, mcp_cli, trust
from fusion_cli.config.mcp_local import upsert_local_mcp_server
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
    yield kok
    mcp_cli.set_session_mcp(None, strict=False)


def test_mcp_config_dosya_ve_metin_ekler_strict_digerlerini_atar(izole, tmp_path):
    upsert_local_mcp_server(izole, McpServerConfig(name="yerel", command="a", scope=McpScope.LOCAL))
    dosya = tmp_path / "mcp.json"
    dosya.write_text(json.dumps({"mcpServers": {"dosyadan": {"command": "b"}}}), encoding="utf-8")
    metin = json.dumps({"mcpServers": {"metinden": {"type": "http", "url": "https://a/mcp"}}})

    mcp_cli.set_session_mcp([str(dosya), metin], strict=False)
    assert {s.name for s in loader.load_config().mcp_servers} == {"yerel", "dosyadan", "metinden"}

    mcp_cli.set_session_mcp([str(dosya)], strict=True)
    assert [s.name for s in loader.load_config().mcp_servers] == ["dosyadan"]


def test_ana_komut_bayraklari_kabul_eder(izole, monkeypatch):
    from typer.testing import CliRunner

    from fusion_cli.cli import app as app_module

    metin = json.dumps({"mcpServers": {"x": {"command": "c"}}})
    result = CliRunner().invoke(
        app_module.app, ["--strict-mcp-config", "--mcp-config", metin, "mcp", "get", "x"]
    )
    assert "x:" in result.output, result.output

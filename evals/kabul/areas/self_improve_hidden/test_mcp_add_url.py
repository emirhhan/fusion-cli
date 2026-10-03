"""Gizli kabul testi: `fusion mcp-add --url/--token-env` (ajanın kopyasına KONMAZ)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.app import app
from fusion_cli.config.loader import load_config
from fusion_cli.config.models import McpTransport

_URL = "https://ornek.test/mcp"
_SECRET_LIKE = "gizli-deger-123"


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("{}\n", encoding="utf-8")
    return path


def _invoke(config_path: Path, argv: list[str]) -> tuple[int, str]:
    env = {"FUSION_CONFIG": str(config_path), "META_TOKEN": _SECRET_LIKE}
    result = CliRunner().invoke(app, argv, env=env)
    return result.exit_code, result.output


def test_url_ile_uzak_sunucu_eklenir(config_path: Path) -> None:
    code, output = _invoke(
        config_path, ["mcp-add", "meta", "--url", _URL, "--token-env", "META_TOKEN"]
    )

    assert code == 0, output
    servers = {server.name: server for server in load_config(config_path).mcp_servers}
    meta = servers["meta"]
    assert meta.transport is McpTransport.STREAMABLE_HTTP
    assert meta.url == _URL
    assert meta.token_env == "META_TOKEN"
    assert meta.command == ""


def test_stdio_yolu_bozulmamis(config_path: Path) -> None:
    code, output = _invoke(config_path, ["mcp-add", "github", "npx", "--", "-y", "x"])

    assert code == 0, output
    servers = {server.name: server for server in load_config(config_path).mcp_servers}
    assert servers["github"].command == "npx"
    assert servers["github"].args == ("-y", "x")
    assert servers["github"].transport is McpTransport.STDIO


def test_command_ve_url_birlikte_hata_verir(config_path: Path) -> None:
    code, _ = _invoke(config_path, ["mcp-add", "x", "npx", "--url", _URL])

    assert code != 0
    assert load_config(config_path).mcp_servers == ()


def test_command_da_url_de_yoksa_hata_verir(config_path: Path) -> None:
    code, _ = _invoke(config_path, ["mcp-add", "x"])

    assert code != 0
    assert load_config(config_path).mcp_servers == ()


def test_token_degeri_degil_yalniz_ad_yazilir(config_path: Path) -> None:
    code, output = _invoke(
        config_path, ["mcp-add", "meta", "--url", _URL, "--token-env", "META_TOKEN"]
    )

    assert code == 0, output
    assert _SECRET_LIKE not in config_path.read_text(encoding="utf-8")
    assert _SECRET_LIKE not in output

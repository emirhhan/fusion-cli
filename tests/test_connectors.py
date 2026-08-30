"""Uygulamadan MCP bağlantısı yönetimi."""

from __future__ import annotations

import pytest

from fusion_cli.appserver import connectors
from fusion_cli.config.models import McpServerConfig
from tests.fakes import make_config


@pytest.fixture
def config(tmp_path):
    return make_config(source=tmp_path / "config.yaml")


def test_komut_satiri_komut_ve_argumanlara_bolunur(config):
    yeni, sonuc = connectors.add_connector(config, {"ad": "github", "komut": "npx -y mcp-github"})

    assert sonuc["ok"] is True
    assert yeni is not None
    assert yeni.mcp_servers[0].command == "npx"
    assert yeni.mcp_servers[0].args == ("-y", "mcp-github")


def test_ayni_ad_iki_kez_eklenemez(config):
    with_one = make_config(
        source=config.source,
        mcp_servers=(McpServerConfig(name="github", command="npx"),),
    )

    _, sonuc = connectors.add_connector(with_one, {"ad": "github", "komut": "npx"})

    assert sonuc["ok"] is False
    assert "zaten var" in sonuc["metin"]


def test_adsiz_ya_da_komutsuz_baglanti_reddedilir(config):
    _, adsiz = connectors.add_connector(config, {"ad": "  ", "komut": "npx"})
    _, komutsuz = connectors.add_connector(config, {"ad": "x", "komut": "  "})

    assert adsiz["ok"] is False
    assert komutsuz["ok"] is False


def test_olmayan_baglanti_silinemez(config):
    _, sonuc = connectors.remove_connector(config, {"ad": "yok"})

    assert sonuc["ok"] is False


def test_silinen_baglanti_dosyaya_yazilir(config):
    with_one = make_config(
        source=config.source,
        mcp_servers=(McpServerConfig(name="github", command="npx"),),
    )

    yeni, sonuc = connectors.remove_connector(with_one, {"ad": "github"})

    assert sonuc["ok"] is True
    assert yeni is not None
    assert yeni.mcp_servers == ()
    assert "mcp_servers: []" in config.source.read_text(encoding="utf-8")


def test_yazma_basarisizsa_degisiklik_uygulanmis_gosterilmez(config, monkeypatch):
    def patla(_config):
        raise OSError("disk dolu")

    monkeypatch.setattr(connectors, "write_mcp_servers", patla)

    yeni, sonuc = connectors.add_connector(config, {"ad": "github", "komut": "npx"})

    assert yeni is None
    assert sonuc["ok"] is False

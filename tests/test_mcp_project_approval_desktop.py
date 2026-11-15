"""Masaüstünde proje `.mcp.json` sunucu onayı (#246): bekleyenler ve üç seçenek."""

from __future__ import annotations

from fusion_cli.appserver.mcp_project_routes import dispatch_mcp_project
from fusion_cli.config import loader
from fusion_cli.config.models import McpScope

from .test_mcp_project_approval import _mcp, izole  # noqa: F401  (fikstür)


def _proje(config):
    return [s.name for s in config.mcp_servers if s.scope is McpScope.PROJECT]


def test_bekleyen_proje_sunuculari_hedefleriyle_listelenir(izole):  # noqa: F811
    _mcp(izole, "github", "linear")

    sonuc, yeni = dispatch_mcp_project("baglanti.proje_bekleyen", {}, izole, loader.load_config())

    assert yeni is None
    assert [s["ad"] for s in sonuc["sunucular"]] == ["github", "linear"]
    assert sonuc["sunucular"][0]["hedef"] == "npx -y github"


def test_bu_sunucuyu_kullan_oturuma_ekler_digeri_bekler(izole):  # noqa: F811
    _mcp(izole, "github", "linear")
    config = loader.load_config()

    sonuc, yeni = dispatch_mcp_project(
        "baglanti.proje_onay", {"ad": "github", "secim": "one"}, izole, config
    )

    assert sonuc["ok"] and [s["ad"] for s in sonuc["sunucular"]] == ["linear"]
    assert yeni is not None and _proje(yeni) == ["github"]
    assert _proje(loader.load_config()) == ["github"]


def test_hepsini_kullan_kalanlari_da_onaylar(izole):  # noqa: F811
    _mcp(izole, "github", "linear")

    sonuc, yeni = dispatch_mcp_project(
        "baglanti.proje_onay", {"ad": "github", "secim": "all"}, izole, loader.load_config()
    )

    assert sonuc["sunucular"] == []
    assert yeni is not None and sorted(_proje(yeni)) == ["github", "linear"]


def test_reddetmek_yuklemez_gecersiz_istek_reddedilir(izole):  # noqa: F811
    _mcp(izole, "github")
    config = loader.load_config()

    sonuc, yeni = dispatch_mcp_project(
        "baglanti.proje_onay", {"ad": "github", "secim": "no"}, izole, config
    )
    assert sonuc["ok"] and yeni is None and sonuc["sunucular"] == []

    hatali, _ = dispatch_mcp_project(
        "baglanti.proje_onay", {"ad": "yok", "secim": "one"}, izole, config
    )
    assert hatali["ok"] is False

"""Uygulamadan MCP bağlantısı yönetimi."""

from __future__ import annotations

import pytest

from fusion_cli.appserver import connectors
from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.client import McpConnectionStatus
from tests.fakes import make_config


@pytest.fixture(autouse=True)
def komutlar_kurulu(monkeypatch):
    """Testler makinenin PATH'ine bağlı kalmasın: her komut "kurulu" sayılır."""
    monkeypatch.setattr(connectors.shutil, "which", lambda command: f"/usr/bin/{command}")


@pytest.fixture
def config(tmp_path):
    return make_config(source=tmp_path / "config.yaml")


def test_komut_satiri_komut_ve_argumanlara_bolunur(config):
    yeni, sonuc = connectors.add_connector(config, {"ad": "github", "komut": "npx -y mcp-github"})

    assert sonuc["ok"] is True
    assert yeni is not None
    assert yeni.mcp_servers[0].command == "npx"
    assert yeni.mcp_servers[0].args == ("-y", "mcp-github")


def test_katalog_argumanlari_ve_sir_adlari_ayri_saklanir(config):
    yeni, sonuc = connectors.add_connector(
        config,
        {
            "ad": "brave",
            "komut": "npx -y @modelcontextprotocol/server-brave-search",
            "argumanlar": ["--safe"],
            "ortam": {"BRAVE_API_KEY": "gizli-deger"},
        },
    )

    assert sonuc["ok"] is True
    assert yeni is not None
    server = yeni.mcp_servers[0]
    assert server.args == ("-y", "@modelcontextprotocol/server-brave-search", "--safe")
    assert server.env_names == ("BRAVE_API_KEY",)
    assert "gizli-deger" not in config.source.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["lowercase", "BAD-NAME", "1TOKEN"])
def test_gecersiz_ortam_degiskeni_adi_reddedilir(config, name):
    _, sonuc = connectors.add_connector(
        config,
        {"ad": "x", "komut": "server", "ortam": {name: "gizli"}},
    )

    assert sonuc["ok"] is False
    assert "ortam değişkeni" in sonuc["metin"]


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


def test_http_baglanti_url_ve_kapsamlarla_eklenir(config):
    yeni, sonuc = connectors.add_connector(
        config,
        {
            "ad": "meta",
            "tasima": "streamable_http",
            "url": "https://mcp.example.com/mcp",
            "kapsamlar": "ads_read business_management",
        },
    )

    assert sonuc["ok"] is True
    assert yeni is not None
    assert yeni.mcp_servers[0].transport is McpTransport.STREAMABLE_HTTP
    assert yeni.mcp_servers[0].url == "https://mcp.example.com/mcp"
    assert yeni.mcp_servers[0].scopes == ("ads_read", "business_management")


def test_guvensiz_uzak_http_baglanti_reddedilir(config):
    _, sonuc = connectors.add_connector(
        config,
        {"ad": "meta", "tasima": "streamable_http", "url": "http://example.com/mcp"},
    )

    assert sonuc["ok"] is False
    assert "HTTPS" in sonuc["metin"]


def test_baglanti_listesi_tasima_ve_saglik_durumunu_verir(config):
    with_one = make_config(
        source=config.source,
        mcp_servers=(McpServerConfig(name="github", command="npx"),),
    )

    sonuc = connectors.list_connectors(
        with_one,
        {"github": {"durum": "bagli", "arac_sayisi": 7, "mesaj": None}},
    )

    row = sonuc["sunucular"][0]
    assert row["tasima"] == "stdio"
    assert row["durum"] == "bagli"
    assert row["arac_sayisi"] == 7


def _yok(_command: str) -> None:
    return None


def test_kurulu_olmayan_calistirici_kaydedilmez_ve_kurulumu_soyler(config):
    """Katalogdaki Fetch uvx istiyordu; uvx yokken "eklendi" deniyordu."""
    yeni, sonuc = connectors.add_connector(
        config, {"ad": "fetch", "komut": "uvx mcp-server-fetch"}, find_command=_yok
    )

    assert yeni is None
    assert sonuc["ok"] is False
    assert sonuc["hata_turu"] == "komut_yok"
    assert "brew install uv" in sonuc["metin"]
    assert not config.source.exists()


def test_ayni_adres_farkli_adla_ikinci_kez_eklenmez(config):
    """Ayarda aynı Meta adresinin üç kopyası birikmişti."""
    with_one = make_config(
        source=config.source,
        mcp_servers=(
            McpServerConfig(
                name="Meta Ads",
                transport=McpTransport.STREAMABLE_HTTP,
                url="https://mcp.facebook.com/ads",
            ),
        ),
    )

    yeni, sonuc = connectors.add_connector(
        with_one,
        {"ad": "Meta 2", "tasima": "streamable_http", "url": "https://MCP.facebook.com/ads/"},
    )

    assert yeni is None
    assert "'Meta Ads' adıyla ekli" in sonuc["metin"]


def test_ayni_komut_farkli_adla_ikinci_kez_eklenmez(config):
    with_one = make_config(
        source=config.source,
        mcp_servers=(McpServerConfig(name="pw", command="npx", args=("-y", "@playwright/mcp")),),
    )

    yeni, _ = connectors.add_connector(
        with_one, {"ad": "pw2", "komut": "npx @playwright/mcp@latest"}
    )

    assert yeni is None


def test_liste_mevcut_kopyalari_silmeden_isaretler(config):
    kopyali = make_config(
        source=config.source,
        mcp_servers=tuple(
            McpServerConfig(
                name=name, transport=McpTransport.STREAMABLE_HTTP, url="https://mcp.x.com/mcp"
            )
            for name in ("meta", "meta-2")
        ),
    )

    rows = {row["ad"]: row for row in connectors.list_connectors(kopyali)["sunucular"]}

    assert "kopyasi" not in rows["meta"]
    assert rows["meta-2"]["kopyasi"] == "meta"
    assert rows["meta-2"]["durum"] == "kopya"
    assert "Kaldır" in rows["meta-2"]["mesaj"]


def _probe(state: str, kind: str | None = None, message: str | None = None):
    async def probe(server):
        return McpConnectionStatus(server=server.name, state=state, kind=kind, message=message)

    return probe


async def test_dogrulanan_eklemede_basarisiz_baglanti_kaydedilmez(config):
    """Var olmayan alan adı "eklendi" oluyordu."""
    yeni, sonuc = await connectors.add_connector_verified(
        config,
        {"ad": "x", "tasima": "streamable_http", "url": "https://yok.invalid/mcp"},
        probe=_probe("hata", "alan_adi_yok", "'yok.invalid' alan adı çözülemedi."),
    )

    assert yeni is None
    assert sonuc["ok"] is False
    assert sonuc["hata_turu"] == "alan_adi_yok"
    assert "çözülemedi" in sonuc["metin"]
    assert not config.source.exists()


async def test_dogrulanan_eklemede_giris_gereken_baglanti_isaretlenip_kaydedilir(config):
    yeni, sonuc = await connectors.add_connector_verified(
        config,
        {"ad": "notion", "tasima": "streamable_http", "url": "https://mcp.notion.com/mcp"},
        probe=_probe("giris_gerekli", "giris_gerekli"),
    )

    assert yeni is not None
    assert sonuc["ok"] is True
    assert sonuc["durum"] == "giris_gerekli"
    assert "notion" in config.source.read_text(encoding="utf-8")


async def test_dogrulanan_eklemede_bagli_sunucu_kaydedilir(config):
    yeni, sonuc = await connectors.add_connector_verified(
        config, {"ad": "pw", "komut": "npx -y @playwright/mcp@latest"}, probe=_probe("bagli")
    )

    assert yeni is not None
    assert sonuc["durum"] == "bagli"
    assert sonuc["metin"] == "'pw' bağlantısı eklendi."

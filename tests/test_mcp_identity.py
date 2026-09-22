"""Aynı sunucuya giden bağlantılar yazım farkına rağmen tanınır."""

from __future__ import annotations

from fusion_cli.config.models import HostedConnectorConfig, McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.identity import (
    connection_identity,
    duplicate_of,
    hosted_duplicate_of,
    unique_configs,
    unique_hosted_configs,
)


def _http(name: str, url: str) -> McpServerConfig:
    return McpServerConfig(name=name, transport=McpTransport.STREAMABLE_HTTP, url=url)


def test_buyuk_harf_sondaki_egik_cizgi_ve_varsayilan_port_ayni_adrestir():
    adresler = (
        "https://mcp.facebook.com/ads",
        "HTTPS://MCP.Facebook.com/ads/",
        "https://mcp.facebook.com:443/ads",
        "  https://mcp.facebook.com/ads  ",
    )

    kimlikler = {connection_identity(_http("meta", url)) for url in adresler}

    assert len(kimlikler) == 1


def test_farkli_yol_ya_da_port_farkli_sunucudur():
    temel = connection_identity(_http("a", "https://mcp.x.com/mcp"))

    assert connection_identity(_http("b", "https://mcp.x.com/sse")) != temel
    assert connection_identity(_http("c", "https://mcp.x.com:8443/mcp")) != temel


def test_npx_kurulum_bayragi_ve_latest_eki_kimligi_degistirmez():
    birinci = McpServerConfig(name="a", command="npx", args=("-y", "@playwright/mcp@latest"))
    ikinci = McpServerConfig(name="b", command="npx", args=("@playwright/mcp",))

    assert connection_identity(birinci) == connection_identity(ikinci)


def test_farkli_klasor_argumani_farkli_sunucudur():
    birinci = McpServerConfig(name="a", command="npx", args=("server-filesystem", "/A"))
    ikinci = McpServerConfig(name="b", command="npx", args=("server-filesystem", "/B"))

    assert connection_identity(birinci) != connection_identity(ikinci)


def test_kopyalar_ilk_kayda_baglanir_ve_ilk_kayit_kalir():
    """Kullanıcının ayarındaki üç Meta kopyası: ilk (asıl) kayıt korunur."""
    configs = (
        _http("Meta Ads", "https://mcp.facebook.com/ads"),
        _http("godot", "https://godot.local.example/mcp"),
        _http("Meta Ads 2", "https://mcp.facebook.com/ads/"),
        _http("Meta Ads 3", "https://MCP.facebook.com/ads"),
    )

    assert duplicate_of(configs) == {"Meta Ads 2": "Meta Ads", "Meta Ads 3": "Meta Ads"}
    assert [config.name for config in unique_configs(configs)] == ["Meta Ads", "godot"]


def _hosted(
    name: str,
    url: str = "https://mcp.facebook.com/ads",
    *,
    provider: str = "chatgpt_web",
    account: str = "main",
    verified: bool = False,
) -> HostedConnectorConfig:
    return HostedConnectorConfig(
        name=name, url=url, provider=provider, account=account, verified=verified
    )


def test_ayni_adrese_giden_iki_connector_kopyadir():
    """Kullanıcının gerçek ayarındaki durum: aynı adres, yalnız ad farklı.

    Ölçüldü (22 Eylül): `hosted_connectors` listesinde "META ADS" ve "Meta Ads"
    kayıtları aynı Meta Ads MCP adresine gidiyordu ve ikisi de kayıt defterine
    ekleniyordu.
    """
    kayitlar = (_hosted("META ADS"), _hosted("Meta Ads"))

    assert hosted_duplicate_of(kayitlar) == {"Meta Ads": "META ADS"}
    assert tuple(item.name for item in unique_hosted_configs(kayitlar)) == ("META ADS",)


def test_farkli_saglayici_kopya_degildir():
    """Aynı MCP adresi iki ayrı sağlayıcı oturumundan bağlıysa iki yetenektir."""
    kayitlar = (_hosted("chatgpt"), _hosted("claude", provider="claude_web"))

    assert hosted_duplicate_of(kayitlar) == {}
    assert len(unique_hosted_configs(kayitlar)) == 2


def test_dogrulanmis_kayit_dogrulanmamis_kopyaya_yenilmez():
    """Doğrulanmamış kayıt listede önce gelse bile doğrulanmış olan kalır."""
    kayitlar = (_hosted("eski", verified=False), _hosted("calisan", verified=True))

    assert tuple(item.name for item in unique_hosted_configs(kayitlar)) == ("calisan",)

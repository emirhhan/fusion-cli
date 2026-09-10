"""Sağlayıcı-barındırmalı connector kurulumunun uygulama tarafı sözleşmesi."""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.appserver.connectors import list_connectors
from fusion_cli.appserver.hosted_connectors import add_hosted_connector, hosted_provider_rows
from fusion_cli.config.models import HostedConnectorConfig, WebSessionConfig

from .fakes import make_config


def _session(provider: str = "claude_web", **extra: object) -> WebSessionConfig:
    base = {
        "model": f"{provider}/main/auto",
        "provider": provider,
        "account": "main",
        "transport": "browser",
        "login_verified": True,
        "enabled": True,
    }
    return WebSessionConfig(**{**base, **extra})  # type: ignore[arg-type]


def test_saglayici_listesi_hazir_olanlari_isaretler():
    """Popup hangi sağlayıcıyı sunacağını veriden öğrenir, tahminle değil."""
    config = replace(make_config(), web_sessions=(_session("claude_web"),))

    rows = hosted_provider_rows(config)

    by_id = {row["id"]: row for row in rows}
    assert by_id["claude_web"]["hazir"] is True
    assert by_id["chatgpt_web"]["hazir"] is False
    # Her satır kullanıcıyı doğru panele götüren adresi taşır.
    assert by_id["claude_web"]["adres"].startswith("https://claude.ai/")


def test_girisi_dogrulanmamis_oturum_hazir_sayilmaz():
    config = replace(make_config(), web_sessions=(_session("claude_web", login_verified=False),))

    by_id = {row["id"]: row for row in hosted_provider_rows(config)}

    assert by_id["claude_web"]["hazir"] is False


def test_connector_ayar_adresi_olmayan_saglayici_sunulmaz():
    """Tahmini bir adres kullanıcıyı var olmayan bir sayfaya yollar."""
    ids = {row["id"] for row in hosted_provider_rows(make_config())}

    assert "copilot_web" not in ids
    assert ids == {"chatgpt_web", "claude_web", "gemini_web"}


def test_hosted_connector_eklenir_ve_dogrulanmamis_baslar():
    config = replace(make_config(), web_sessions=(_session(),))

    yeni, sonuc = add_hosted_connector(
        config,
        {"ad": "Meta Ads", "url": "https://mcp.facebook.com/ads", "saglayici": "claude_web"},
    )

    assert sonuc["ok"] is True, sonuc
    assert yeni is not None
    kayit = yeni.hosted_connectors[0]
    assert kayit.provider == "claude_web"
    assert kayit.verified is False
    # Kullanıcıya hangi adresi nereye yapıştıracağı söylenir.
    assert sonuc["adres"].startswith("https://claude.ai/")


def test_oturumu_olmayan_saglayiciya_eklenemez():
    _, sonuc = add_hosted_connector(
        make_config(),
        {"ad": "Meta Ads", "url": "https://mcp.facebook.com/ads", "saglayici": "claude_web"},
    )

    assert sonuc["ok"] is False
    assert "oturum" in sonuc["metin"]


def test_listede_hosted_connector_tasimasiyla_gorunur():
    config = replace(
        make_config(),
        web_sessions=(_session(),),
        hosted_connectors=(
            HostedConnectorConfig(
                name="Meta Ads",
                url="https://mcp.facebook.com/ads",
                provider="claude_web",
                verified=True,
            ),
        ),
    )

    rows = list_connectors(config)["sunucular"]

    hosted = [row for row in rows if row["tasima"] == "hosted"]
    assert len(hosted) == 1
    assert hosted[0]["ad"] == "Meta Ads"
    assert hosted[0]["saglayici"] == "claude_web"
    # Oturum bağlı olduğu için çalışabilir; bu bilgi arayüzdeki uyarıyı besler.
    assert hosted[0]["hazir"] is True


async def test_dogrulama_araclari_sayar_ve_kaydi_dogrulanmis_yapar():
    """`verified` bayrağını açan tek yol budur; aksi hâlde özellik hiç çalışmaz.

    Ölçülmüş boşluk (inceleme): kurulum akışı sonuna kadar izlense bile
    `register_into` doğrulanmamış connector'ı atlıyor, `added` hep boş kalıyor ve
    kullanıcı sebebi göremiyordu.
    """
    from fusion_cli.appserver.hosted_connectors import verify_hosted_connector

    config = replace(
        make_config(),
        web_sessions=(_session(),),
        hosted_connectors=(
            HostedConnectorConfig(
                name="Meta Ads",
                url="https://mcp.facebook.com/ads",
                provider="claude_web",
            ),
        ),
    )

    async def kesif(connector):
        del connector
        return ("get_campaigns", "set_budget")

    yeni, sonuc = await verify_hosted_connector(config, {"ad": "Meta Ads"}, discover=kesif)

    assert sonuc["ok"] is True, sonuc
    assert sonuc["arac_sayisi"] == 2
    assert yeni is not None
    assert yeni.hosted_connectors[0].verified is True


async def test_kesif_bos_donerse_dogrulanmis_sayilmaz():
    """Araç bulunamadıysa connector hazır değildir; yeşil göstermek yalan olurdu."""
    from fusion_cli.appserver.hosted_connectors import verify_hosted_connector

    config = replace(
        make_config(),
        web_sessions=(_session(),),
        hosted_connectors=(
            HostedConnectorConfig(
                name="Meta Ads", url="https://mcp.facebook.com/ads", provider="claude_web"
            ),
        ),
    )

    async def bos(connector):
        del connector
        return ()

    yeni, sonuc = await verify_hosted_connector(config, {"ad": "Meta Ads"}, discover=bos)

    assert sonuc["ok"] is False
    assert yeni is None
    assert "araç" in sonuc["metin"]


async def test_kesif_hatasi_kullaniciya_tasinir():
    from fusion_cli.appserver.hosted_connectors import verify_hosted_connector

    config = replace(
        make_config(),
        web_sessions=(_session(),),
        hosted_connectors=(
            HostedConnectorConfig(
                name="Meta Ads", url="https://mcp.facebook.com/ads", provider="claude_web"
            ),
        ),
    )

    async def patla(connector):
        del connector
        raise RuntimeError("oturum düştü")

    yeni, sonuc = await verify_hosted_connector(config, {"ad": "Meta Ads"}, discover=patla)

    assert yeni is None
    assert "oturum düştü" in sonuc["metin"]

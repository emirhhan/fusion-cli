"""Sağlayıcı-barındırmalı connector: web oturumu üzerinden çalışan uzak MCP.

Neden bu model var: Meta gibi sunucular dinamik istemci kaydını reddediyor ve
başkalarının reklam hesabına OAuth ile girebilmek Meta'da App Review gerektiriyor.
Buna karşılık kullanıcı AYNI sunucuyu ChatGPT/Claude/Gemini'nin kendi connector
ekranından tek bir girişle bağlayabiliyor — çünkü o istemciler onaylı. Fusion bu
sunucuya MCP KONUŞMAZ: araçlar sağlayıcının ajan döngüsünde yaşar, Fusion onları
zaten sürdüğü web oturumuna yazıp okuyarak kullanır.
"""

from __future__ import annotations

from fusion_cli.config.models import HostedConnectorConfig, WebSessionConfig
from fusion_cli.config.writer import write_hosted_connectors
from fusion_cli.providers.web_browser import provider_definition

from .fakes import make_config


def _connector(**extra: object) -> HostedConnectorConfig:
    base = {
        "name": "Meta Ads",
        "url": "https://mcp.facebook.com/ads",
        "provider": "claude_web",
        "account": "main",
    }
    return HostedConnectorConfig(**{**base, **extra})  # type: ignore[arg-type]


def _session(**extra: object) -> WebSessionConfig:
    base = {
        "model": "claude_web/main/auto",
        "provider": "claude_web",
        "account": "main",
        "transport": "browser",
        "login_verified": True,
        "enabled": True,
    }
    return WebSessionConfig(**{**base, **extra})  # type: ignore[arg-type]


def test_dogrulanmamis_connector_varsayilan_olarak_kapalidir():
    """Ölçülmeyen bir connector araç olarak kaydedilmez (tool_eval_passed deseni)."""
    assert _connector().verified is False


def test_her_saglayicinin_connector_ayar_adresi_vardir():
    """Popup "sağlayıcının sitesini aç" derken adres sağlayıcıya göre değişir."""
    adresler = {
        name: provider_definition(name).connector_settings_url
        for name in ("claude_web", "chatgpt_web", "gemini_web")
    }

    assert all(adres.startswith("https://") for adres in adresler.values()), adresler
    # Üçü birbirinden farklı olmalı: tek bir adrese yönlendirmek kullanıcıyı yanlış
    # panele götürürdü.
    assert len(set(adresler.values())) == 3


def test_connector_yazilip_geri_okunur(tmp_path):
    """Connector kalıcıdır; her oturumda yeniden kurulmamalı."""
    from dataclasses import replace

    from fusion_cli.config.loader import load_config

    hedef = tmp_path / "config.yaml"
    config = replace(
        make_config(source=hedef),
        web_sessions=(_session(),),
        hosted_connectors=(_connector(verified=True),),
    )

    write_hosted_connectors(config, hedef)
    geri = load_config(hedef)

    assert len(geri.hosted_connectors) == 1
    kayit = geri.hosted_connectors[0]
    assert kayit.name == "Meta Ads"
    assert kayit.url == "https://mcp.facebook.com/ads"
    assert kayit.provider == "claude_web"
    assert kayit.verified is True


def test_oturumu_olmayan_connector_calisamaz_olarak_isaretlenir():
    """UI'ın göstereceği uyarı verinin kendisinden çıkmalı, tahminle değil."""
    from fusion_cli.config.models import hosted_connector_ready

    config = make_config()
    bagli = _connector(verified=True)

    assert hosted_connector_ready(config, bagli) is False

    from dataclasses import replace

    with_session = replace(config, web_sessions=(_session(),))
    assert hosted_connector_ready(with_session, bagli) is True

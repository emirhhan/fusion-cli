"""Sağlayıcı-barındırmalı connector'ların uygulama tarafı.

Ayrı modüldedir: `connectors.py` Fusion'ın KENDİ kurduğu MCP bağlantılarını
yönetir, burası ise sağlayıcının connector ekranında yaşayan bağlantıları. İki
akışın doğrulaması, hata mesajları ve kalıcılığı farklıdır; tek dosyada
toplamak ikisini de okunmaz yapardı (RULES: özellik/alana göre böl).

Burada SIR YOKTUR: kimlik doğrulama sağlayıcının kendi oturumunda yapılır ve
token Fusion'a hiç gelmez. Bu, modelin var olma gerekçesidir.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..config.models import Config, HostedConnectorConfig, hosted_connector_ready
from ..config.writer import write_hosted_connectors
from ..mcp_bridge.oauth import validate_remote_mcp_url
from ..providers.web_browser import WEB_BROWSER_PROVIDERS, provider_definition

__all__ = [
    "add_hosted_connector",
    "hosted_connector_rows",
    "hosted_provider_rows",
    "remove_hosted_connector",
]


def hosted_provider_rows(config: Config) -> list[dict[str, Any]]:
    """Kurulum ekranının sunacağı sağlayıcılar ve hazır olup olmadıkları.

    Yalnız `connector_settings_url` TANIMLI sağlayıcılar sunulur: tahmini bir
    adres kullanıcıyı var olmayan bir sayfaya yollar (bkz.
    `BrowserProviderDefinition.connector_settings_url`).

    `hazir` bir tahmin değil yapılandırmadan okunan olgudur; arayüzdeki "hiçbir
    web sağlayıcısına bağlı değilsiniz" uyarısını da bu besler.
    """
    rows: list[dict[str, Any]] = []
    for provider_id, definition in WEB_BROWSER_PROVIDERS.items():
        if not definition.connector_settings_url:
            continue
        rows.append(
            {
                "id": provider_id,
                "ad": definition.name,
                "adres": definition.connector_settings_url,
                "hazir": _ready_provider(config, provider_id),
            }
        )
    return rows


def _ready_provider(config: Config, provider_id: str) -> bool:
    probe = HostedConnectorConfig(name="", url="", provider=provider_id, account="main")
    return hosted_connector_ready(config, probe)


def hosted_connector_rows(config: Config) -> list[dict[str, Any]]:
    """Kayıtlı barındırmalı connector'ları bağlantı listesine uygun biçimde ver."""
    return [
        {
            "ad": connector.name,
            "tasima": "hosted",
            "url": connector.url,
            "saglayici": connector.provider,
            "hesap": connector.account,
            "dogrulandi": connector.verified,
            # Oturum düşmüşse araçlar çalışmaz; arayüz bunu uyarı olarak gösterir.
            "hazir": hosted_connector_ready(config, connector),
            "durum": "bagli" if connector.verified else "yapilandirildi",
        }
        for connector in config.hosted_connectors
    ]


def add_hosted_connector(config: Config, data: object) -> tuple[Config | None, dict[str, Any]]:
    """`baglanti.saglayici_ekle`: connector'ı bir web oturumuna bağla.

    Kayıt `verified=False` başlar. Ölçüm yapılmadan araçları kaydetmek, modelin
    var olmayan yeteneklere güvenmesine yol açar — `tool_eval_passed` ile aynı
    gerekçe.
    """
    if not isinstance(data, dict):
        return None, {"ok": False, "metin": "Geçersiz bağlantı."}
    ad = str(data.get("ad", "")).strip()
    url = str(data.get("url", "")).strip()
    saglayici = str(data.get("saglayici", "")).strip()
    hesap = str(data.get("hesap", "") or "main").strip()
    if not ad:
        return None, {"ok": False, "metin": "Bağlantının bir adı olmalı."}
    if saglayici not in WEB_BROWSER_PROVIDERS:
        return None, {"ok": False, "metin": "Geçersiz web sağlayıcısı."}
    definition = provider_definition(saglayici)
    if not definition.connector_settings_url:
        return None, {
            "ok": False,
            "metin": f"{definition.name} connector eklemeyi desteklemiyor.",
        }
    try:
        validate_remote_mcp_url(url)
    except ValueError as error:
        return None, {"ok": False, "metin": str(error)}
    if any(item.name == ad for item in config.hosted_connectors):
        return None, {"ok": False, "metin": f"'{ad}' adlı bağlantı zaten var."}
    connector = HostedConnectorConfig(name=ad, url=url, provider=saglayici, account=hesap)
    if not hosted_connector_ready(config, connector):
        return None, {
            "ok": False,
            "metin": (
                f"{definition.name} oturumu bağlı değil. Bu bağlantı araçlarını o "
                "oturum üzerinden çalıştırır; önce sağlayıcıya giriş yap."
            ),
        }
    yeni = replace(config, hosted_connectors=(*config.hosted_connectors, connector))
    try:
        write_hosted_connectors(yeni)
    except Exception as error:
        return None, {"ok": False, "metin": f"Bağlantı kaydedilemedi: {error}"}
    return yeni, {
        "ok": True,
        "ad": ad,
        # Kullanıcı bu adresi sağlayıcının panelinde MCP adresi olarak yapıştırır.
        "mcp_adresi": url,
        # ...ve panel burada açılır.
        "adres": definition.connector_settings_url,
        "saglayici": saglayici,
    }


def remove_hosted_connector(config: Config, data: object) -> tuple[Config | None, dict[str, Any]]:
    """`baglanti.saglayici_sil`: barındırmalı connector kaydını kaldır."""
    if not isinstance(data, dict):
        return None, {"ok": False, "metin": "Geçersiz bağlantı."}
    ad = str(data.get("ad", "")).strip()
    kalan = tuple(item for item in config.hosted_connectors if item.name != ad)
    if len(kalan) == len(config.hosted_connectors):
        return None, {"ok": False, "metin": f"'{ad}' adlı bağlantı bulunamadı."}
    yeni = replace(config, hosted_connectors=kalan)
    try:
        write_hosted_connectors(yeni)
    except Exception as error:
        return None, {"ok": False, "metin": f"Bağlantı kaldırılamadı: {error}"}
    return yeni, {"ok": True, "ad": ad}

"""MCP sunucu bağlantılarını uygulamadan yönet.

MCP sunucusu eklemek için kullanıcı `config.yaml`'ı elle açmak zorunda
kalıyordu. Ekleme ve kaldırma burada yapılır; yazma işi `config.writer`'a
bırakılır çünkü kilitleme ve atomik yazma orada çözülmüş durumda.

Agent'ın kendi dosya araçlarıyla yapılandırmaya yazmasına izin verilmez; bu yol
YALNIZCA kullanıcının arayüzdeki açık eylemiyle çalışır.
"""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ..config.models import Config, McpServerConfig, McpTransport
from ..config.writer import write_mcp_servers
from ..mcp_bridge.client import McpConnectionStatus
from ..mcp_bridge.oauth import validate_remote_mcp_url


def status_payload(status: McpConnectionStatus) -> dict[str, Any]:
    return {
        "ok": status.state == "bagli",
        "ad": status.server,
        "durum": status.state,
        "arac_sayisi": status.tool_count,
        "gecikme_ms": status.latency_ms,
        "mesaj": status.message,
    }


def list_connectors(
    config: Config, statuses: Mapping[str, McpConnectionStatus | dict[str, Any]] | None = None
) -> dict[str, Any]:
    """`baglanti.listele`: bağlı MCP sunucuları."""
    return {
        "ok": True,
        "sunucular": [
            {
                "ad": server.name,
                "komut": server.command,
                "argumanlar": list(server.args),
                "tasima": server.transport.value,
                "url": server.url,
                "kapsamlar": list(server.scopes),
                "client_id": server.client_id,
                **_row_status((statuses or {}).get(server.name)),
            }
            for server in config.mcp_servers
        ],
    }


def _row_status(status: McpConnectionStatus | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(status, McpConnectionStatus):
        return {
            "durum": status.state,
            "arac_sayisi": status.tool_count,
            "gecikme_ms": status.latency_ms,
            "mesaj": status.message,
        }
    if isinstance(status, dict):
        return {
            "durum": str(status.get("durum", "yapilandirildi")),
            "arac_sayisi": int(status.get("arac_sayisi", 0)),
            "gecikme_ms": int(status.get("gecikme_ms", 0)),
            "mesaj": status.get("mesaj"),
        }
    return {"durum": "yapilandirildi", "arac_sayisi": 0, "gecikme_ms": 0, "mesaj": None}


def add_connector(config: Config, data: object) -> tuple[Config | None, dict[str, Any]]:
    """`baglanti.ekle`: yeni MCP sunucusu tanımla.

    Komut satırı `shlex` ile ayrıştırılır: kullanıcı "npx -y foo" yazdığında
    tek parça bir komut yerine komut + argümanlar elde edilir. Kabuk
    ÇALIŞTIRILMAZ; ayrıştırma yalnız metni parçalara böler.
    """
    if not isinstance(data, dict):
        return None, {"ok": False, "metin": "Geçersiz bağlantı."}
    ad = str(data.get("ad", "")).strip()
    raw_transport = str(data.get("tasima", McpTransport.STDIO.value)).strip()
    try:
        transport = McpTransport(raw_transport)
    except ValueError:
        return None, {"ok": False, "metin": "Geçersiz MCP bağlantı türü."}
    ham = str(data.get("komut", "")).strip()
    url = str(data.get("url", "")).strip()
    if not ad:
        return None, {"ok": False, "metin": "Bağlantının bir adı olmalı."}
    if transport is McpTransport.STDIO and not ham:
        return None, {"ok": False, "metin": "Çalıştırılacak komut boş olamaz."}
    if any(server.name == ad for server in config.mcp_servers):
        return None, {"ok": False, "metin": f"'{ad}' adlı bağlantı zaten var."}
    if transport is McpTransport.STDIO:
        try:
            parcalar = shlex.split(ham)
        except ValueError as error:
            return None, {"ok": False, "metin": f"Komut ayrıştırılamadı: {error}"}
        if not parcalar:
            return None, {"ok": False, "metin": "Çalıştırılacak komut boş olamaz."}
        sunucu = McpServerConfig(name=ad, command=parcalar[0], args=tuple(parcalar[1:]))
    else:
        try:
            validate_remote_mcp_url(url)
        except ValueError as error:
            return None, {"ok": False, "metin": str(error)}
        scopes = tuple(str(data.get("kapsamlar", "")).split())
        sunucu = McpServerConfig(
            name=ad,
            transport=transport,
            url=url,
            scopes=scopes,
            client_id=str(data.get("client_id", "")).strip(),
        )
    yeni = replace(config, mcp_servers=(*config.mcp_servers, sunucu))
    return _persist(yeni, f"'{ad}' bağlantısı eklendi.")


def remove_connector(config: Config, data: object) -> tuple[Config | None, dict[str, Any]]:
    """`baglanti.sil`: MCP sunucusunu kaldır."""
    if not isinstance(data, dict):
        return None, {"ok": False, "metin": "Geçersiz bağlantı."}
    ad = str(data.get("ad", "")).strip()
    kalan = tuple(server for server in config.mcp_servers if server.name != ad)
    if len(kalan) == len(config.mcp_servers):
        return None, {"ok": False, "metin": f"'{ad}' adlı bağlantı yok."}
    return _persist(replace(config, mcp_servers=kalan), f"'{ad}' bağlantısı kaldırıldı.")


def _persist(config: Config, message: str) -> tuple[Config | None, dict[str, Any]]:
    """Yapılandırmayı yaz. Yazma başarısızsa bellekteki hâli DE değiştirilmez:
    kaydedilmemiş bir değişikliği uygulanmış göstermek yanıltıcı olurdu."""
    try:
        write_mcp_servers(config)
    except Exception as error:  # ConfigError ve OSError türevleri
        return None, {"ok": False, "metin": f"Bağlantı kaydedilemedi: {error}"}
    return config, {"ok": True, "metin": message}

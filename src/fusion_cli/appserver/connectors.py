"""MCP sunucu bağlantılarını uygulamadan yönet.

MCP sunucusu eklemek için kullanıcı `config.yaml`'ı elle açmak zorunda
kalıyordu. Ekleme ve kaldırma burada yapılır; yazma işi `config.writer`'a
bırakılır çünkü kilitleme ve atomik yazma orada çözülmüş durumda.

Agent'ın kendi dosya araçlarıyla yapılandırmaya yazmasına izin verilmez; bu yol
YALNIZCA kullanıcının arayüzdeki açık eylemiyle çalışır.
"""

from __future__ import annotations

import shlex
from dataclasses import replace
from typing import Any

from ..config.models import Config, McpServerConfig
from ..config.writer import write_mcp_servers


def list_connectors(config: Config) -> dict[str, Any]:
    """`baglanti.listele`: bağlı MCP sunucuları."""
    return {
        "ok": True,
        "sunucular": [
            {"ad": server.name, "komut": server.command, "argumanlar": list(server.args)}
            for server in config.mcp_servers
        ],
    }


def add_connector(config: Config, data: object) -> tuple[Config | None, dict[str, Any]]:
    """`baglanti.ekle`: yeni MCP sunucusu tanımla.

    Komut satırı `shlex` ile ayrıştırılır: kullanıcı "npx -y foo" yazdığında
    tek parça bir komut yerine komut + argümanlar elde edilir. Kabuk
    ÇALIŞTIRILMAZ; ayrıştırma yalnız metni parçalara böler.
    """
    if not isinstance(data, dict):
        return None, {"ok": False, "metin": "Geçersiz bağlantı."}
    ad = str(data.get("ad", "")).strip()
    ham = str(data.get("komut", "")).strip()
    if not ad:
        return None, {"ok": False, "metin": "Bağlantının bir adı olmalı."}
    if not ham:
        return None, {"ok": False, "metin": "Çalıştırılacak komut boş olamaz."}
    if any(server.name == ad for server in config.mcp_servers):
        return None, {"ok": False, "metin": f"'{ad}' adlı bağlantı zaten var."}
    try:
        parcalar = shlex.split(ham)
    except ValueError as error:
        return None, {"ok": False, "metin": f"Komut ayrıştırılamadı: {error}"}
    if not parcalar:
        return None, {"ok": False, "metin": "Çalıştırılacak komut boş olamaz."}

    sunucu = McpServerConfig(name=ad, command=parcalar[0], args=tuple(parcalar[1:]))
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

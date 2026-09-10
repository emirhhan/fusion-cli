"""MCP sunucu bağlantılarını uygulamadan yönet.

MCP sunucusu eklemek için kullanıcı `config.yaml`'ı elle açmak zorunda
kalıyordu. Ekleme ve kaldırma burada yapılır; yazma işi `config.writer`'a
bırakılır çünkü kilitleme ve atomik yazma orada çözülmüş durumda.

Agent'ın kendi dosya araçlarıyla yapılandırmaya yazmasına izin verilmez; bu yol
YALNIZCA kullanıcının arayüzdeki açık eylemiyle çalışır.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ..config.models import Config, McpServerConfig, McpTransport
from ..config.writer import write_mcp_servers
from ..mcp_bridge.client import McpConnectionStatus
from ..mcp_bridge.oauth import validate_remote_mcp_url
from .hosted_connectors import hosted_connector_rows

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_MAX_SECRET_CHARS = 8_192
#: Türetilen token ortam değişkenlerinin ortak öneki.
_TOKEN_PREFIX = "FUSION_MCP_TOKEN_"


def token_env_name(connector_name: str) -> str:
    """Bağlantı adından token'ın ortam değişkeni adını türet.

    Kullanıcıdan ayrıca bir değişken adı istemek gereksiz bir adımdı: token tek
    bir bağlantıya aittir ve adı oradan belirlenir.
    """
    slug = re.sub(r"[^A-Za-z0-9]+", "_", connector_name).strip("_").upper()
    return f"{_TOKEN_PREFIX}{slug}" if slug else ""


def connector_secret_values(data: object) -> tuple[dict[str, str], str | None]:
    """RPC girdisindeki sırları doğrula; değerleri hiçbir yanıta ekleme.

    Uzak sunucunun erişim token'ı da buradan geçer: çağıran (`_add_connector`)
    sırları şifreli depoya yazıp geri alma akışını zaten çözmüş durumda.
    """
    if not isinstance(data, dict):
        return {}, None
    token, token_error = _token_secret(data)
    if token_error is not None:
        return {}, token_error
    raw = data.get("ortam", {})
    if raw is None:
        return {}, None
    if not isinstance(raw, dict):
        return {}, "MCP ortam değişkenleri sözlük olmalı."
    values: dict[str, str] = {}
    for raw_name, raw_value in raw.items():
        name = str(raw_name).strip()
        if not _ENV_NAME.fullmatch(name):
            return {}, f"Geçersiz MCP ortam değişkeni adı: {name or '(boş)'}"
        if not isinstance(raw_value, str):
            return {}, f"{name} değeri metin olmalı."
        value = raw_value
        if not value or len(value) > _MAX_SECRET_CHARS:
            return {}, f"{name} değeri boş olamaz ve {_MAX_SECRET_CHARS} karakteri aşamaz."
        values[name] = value
    return {**token, **values}, None


def _token_secret(data: Mapping[str, Any]) -> tuple[dict[str, str], str | None]:
    """`token` alanını türetilmiş ortam adına bağla."""
    raw = data.get("token")
    if raw is None:
        return {}, None
    if not isinstance(raw, str):
        return {}, "MCP erişim token'ı metin olmalı."
    value = raw.strip()
    if not value:
        return {}, None
    if len(value) > _MAX_SECRET_CHARS:
        return {}, f"MCP erişim token'ı {_MAX_SECRET_CHARS} karakteri aşamaz."
    name = token_env_name(str(data.get("ad", "")).strip())
    if not name:
        return {}, "Token kaydetmek için bağlantının bir adı olmalı."
    return {name: value}, None


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
                "ortam_degiskenleri": list(server.env_names),
                # Yalnız token'ın VAR olduğu bildirilir; değer hiçbir yanıta girmez.
                "token_var": bool(server.token_env),
                **_row_status((statuses or {}).get(server.name)),
            }
            for server in config.mcp_servers
        ]
        # Barındırmalı connector'lar aynı listede görünür: kullanıcı için ikisi de
        # "bağlantı"dır, farkı `tasima` alanı taşır.
        + hosted_connector_rows(config),
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
    secrets, secret_error = connector_secret_values(data)
    if secret_error is not None:
        return None, {"ok": False, "metin": secret_error}
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
        raw_args = data.get("argumanlar", [])
        if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
            return None, {"ok": False, "metin": "MCP komut argümanları metin listesi olmalı."}
        sunucu = McpServerConfig(
            name=ad,
            command=parcalar[0],
            args=(*parcalar[1:], *(item for item in raw_args if item)),
            env_names=tuple(secrets),
        )
    else:
        try:
            validate_remote_mcp_url(url)
        except ValueError as error:
            return None, {"ok": False, "metin": str(error)}
        scopes = tuple(str(data.get("kapsamlar", "")).split())
        token_env = token_env_name(ad) if token_env_name(ad) in secrets else ""
        sunucu = McpServerConfig(
            name=ad,
            transport=transport,
            url=url,
            scopes=scopes,
            client_id=str(data.get("client_id", "")).strip(),
            token_env=token_env,
            env_names=(token_env,) if token_env else (),
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

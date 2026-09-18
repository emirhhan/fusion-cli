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
import shutil
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from typing import Any

from ..config.models import Config, McpServerConfig, McpTransport
from ..config.writer import write_mcp_servers
from ..mcp_bridge.client import McpConnectionStatus
from ..mcp_bridge.failures import (
    STATE_CONNECTED,
    STATE_LOGIN_REQUIRED,
    missing_command_failure,
)
from ..mcp_bridge.identity import connection_identity, duplicate_of
from ..mcp_bridge.oauth import DEFAULT_CALLBACK_PORT, validate_remote_mcp_url
from .hosted_connectors import hosted_connector_rows

#: Komutun PATH'te olup olmadığını söyleyen arama (test yerine geçebilsin diye).
CommandFinder = Callable[[str], str | None]
#: Kaydetmeden önce bağlantıyı deneyen yoklama (bkz. `McpConnectionService.verify`).
ConnectorProbe = Callable[[McpServerConfig], Awaitable[McpConnectionStatus]]

#: Kaydedilebilir yoklama sonuçları. "Giriş gerekli" BOZUK değildir: sunucu
#: çalışıyor ve kullanıcının "Bağlan" demesini bekliyor.
_SAVEABLE_STATES = frozenset({STATE_CONNECTED, STATE_LOGIN_REQUIRED})

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
        "hata_turu": status.kind,
    }


def list_connectors(
    config: Config, statuses: Mapping[str, McpConnectionStatus | dict[str, Any]] | None = None
) -> dict[str, Any]:
    """`baglanti.listele`: bağlı MCP sunucuları.

    Aynı sunucuya giden kopyalar SİLİNMEZ (kullanıcı verisidir) ama işaretlenir:
    turlarda yalnız ilk kayıt bağlanır ve satır kullanıcıya hangisinin fazla
    olduğunu söyler (bkz. `mcp_bridge/identity.py::duplicate_of`).
    """
    duplicates = duplicate_of(config.mcp_servers)
    return {
        "ok": True,
        # Kullanıcı bunu sağlayıcının OAuth panelinde "geçerli yönlendirme adresi"
        # olarak kaydeder. Arayüzde gösterilmesi zorunlu: adres birebir eşleşmeli
        # ve portu tahmin etmek zorunda kalmamalı (bkz. `oauth.DEFAULT_CALLBACK_PORT`).
        "oauth_donus_adresi": f"http://localhost:{DEFAULT_CALLBACK_PORT}/oauth/callback",
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
                **_duplicate_fields(duplicates.get(server.name)),
            }
            for server in config.mcp_servers
        ]
        # Barındırmalı connector'lar aynı listede görünür: kullanıcı için ikisi de
        # "bağlantı"dır, farkı `tasima` alanı taşır.
        + hosted_connector_rows(config),
    }


def _duplicate_fields(original: str | None) -> dict[str, Any]:
    if original is None:
        return {}
    return {
        "kopyasi": original,
        "durum": "kopya",
        "mesaj": (
            f"Bu bağlantı '{original}' ile aynı sunucuya gidiyor; turlarda yalnız "
            f"'{original}' kullanılır. Fazlasını Kaldır ile silebilirsin."
        ),
    }


def _row_status(status: McpConnectionStatus | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(status, McpConnectionStatus):
        return {
            "durum": status.state,
            "arac_sayisi": status.tool_count,
            "gecikme_ms": status.latency_ms,
            "mesaj": status.message,
            "hata_turu": status.kind,
        }
    if isinstance(status, dict):
        return {
            "durum": str(status.get("durum", "yapilandirildi")),
            "arac_sayisi": int(status.get("arac_sayisi", 0)),
            "gecikme_ms": int(status.get("gecikme_ms", 0)),
            "mesaj": status.get("mesaj"),
        }
    return {"durum": "yapilandirildi", "arac_sayisi": 0, "gecikme_ms": 0, "mesaj": None}


def add_connector(
    config: Config, data: object, *, find_command: CommandFinder = shutil.which
) -> tuple[Config | None, dict[str, Any]]:
    """`baglanti.ekle`: yeni MCP sunucusu tanımla ve kaydet.

    Kaydetmeden önce çalıştırılamayacağı KESİN olan bağlantı reddedilir: aynı
    sunucunun ikinci kopyası ve PATH'te olmayan komut (ör. `uvx` kurulu değil).
    Ölçüldü (17 Eylül): ikisi de "eklendi" deniyordu; kopyalar birikiyor, bozuk
    bağlantı her turda yeniden deneniyordu.
    """
    server, error = build_connector(config, data, find_command=find_command)
    if server is None:
        return None, error
    yeni = replace(config, mcp_servers=(*config.mcp_servers, server))
    return _persist(yeni, f"'{server.name}' bağlantısı eklendi.")


async def add_connector_verified(
    config: Config,
    data: object,
    *,
    probe: ConnectorProbe,
    find_command: CommandFinder = shutil.which,
) -> tuple[Config | None, dict[str, Any]]:
    """`baglanti.ekle`'nin DOĞRULAYAN hâli: önce bağlan, başarılıysa kaydet.

    Ölçüldü (17 Eylül): var olmayan alan adı ve geçersiz token "eklendi" oluyordu.
    Yoklama başarısızsa hiçbir şey yazılmaz ve sınıflandırılmış hata (ne oldu, ne
    yapmalı) döner. "Giriş gerekli" kaydedilir ve öyle işaretlenir: sunucu
    sağlam, yalnız kullanıcının "Bağlan" demesini bekliyor.

    `probe` giriş penceresi AÇMAMALIDIR (bkz. `McpConnectionService.verify`); sır
    gerektiren bağlantıda çağıran, sırları yoklamadan ÖNCE ortama yüklemelidir.
    """
    server, error = build_connector(config, data, find_command=find_command)
    if server is None:
        return None, error
    status = await probe(server)
    if status.state not in _SAVEABLE_STATES:
        return None, {**status_payload(status), "ok": False, "metin": status.message}
    yeni, sonuc = _persist(
        replace(config, mcp_servers=(*config.mcp_servers, server)),
        f"'{server.name}' bağlantısı eklendi.",
    )
    if yeni is None:
        return None, sonuc
    return yeni, {**status_payload(status), **sonuc, "ok": True}


def build_connector(
    config: Config, data: object, *, find_command: CommandFinder = shutil.which
) -> tuple[McpServerConfig | None, dict[str, Any]]:
    """RPC girdisini doğrulanmış bir `McpServerConfig`'e çevir; yazmaz.

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
    secrets, secret_error = connector_secret_values(data)
    if secret_error is not None:
        return None, {"ok": False, "metin": secret_error}
    if not ad:
        return None, {"ok": False, "metin": "Bağlantının bir adı olmalı."}
    if any(server.name == ad for server in config.mcp_servers):
        return None, {"ok": False, "metin": f"'{ad}' adlı bağlantı zaten var."}
    if transport is McpTransport.STDIO:
        server, error = _stdio_server(ad, data, secrets, find_command)
    else:
        server, error = _remote_server(ad, transport, data, secrets)
    if server is None:
        return None, error
    return _reject_duplicate(config, server)


def _stdio_server(
    ad: str, data: Mapping[str, Any], secrets: Mapping[str, str], find_command: CommandFinder
) -> tuple[McpServerConfig | None, dict[str, Any]]:
    ham = str(data.get("komut", "")).strip()
    try:
        parcalar = shlex.split(ham)
    except ValueError as error:
        return None, {"ok": False, "metin": f"Komut ayrıştırılamadı: {error}"}
    if not parcalar:
        return None, {"ok": False, "metin": "Çalıştırılacak komut boş olamaz."}
    raw_args = data.get("argumanlar", [])
    if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
        return None, {"ok": False, "metin": "MCP komut argümanları metin listesi olmalı."}
    if find_command(parcalar[0]) is None:
        failure = missing_command_failure(parcalar[0])
        return None, {"ok": False, "metin": failure.message, "hata_turu": failure.kind.value}
    return McpServerConfig(
        name=ad,
        command=parcalar[0],
        args=(*parcalar[1:], *(item for item in raw_args if item)),
        env_names=tuple(secrets),
    ), {}


def _remote_server(
    ad: str, transport: McpTransport, data: Mapping[str, Any], secrets: Mapping[str, str]
) -> tuple[McpServerConfig | None, dict[str, Any]]:
    url = str(data.get("url", "")).strip()
    try:
        validate_remote_mcp_url(url)
    except ValueError as error:
        return None, {"ok": False, "metin": str(error)}
    token_env = token_env_name(ad) if token_env_name(ad) in secrets else ""
    return McpServerConfig(
        name=ad,
        transport=transport,
        url=url,
        scopes=tuple(str(data.get("kapsamlar", "")).split()),
        client_id=str(data.get("client_id", "")).strip(),
        token_env=token_env,
        env_names=(token_env,) if token_env else (),
    ), {}


def _reject_duplicate(
    config: Config, server: McpServerConfig
) -> tuple[McpServerConfig | None, dict[str, Any]]:
    """Aynı adrese/komuta giden ikinci bağlantıyı ekleme."""
    identity = connection_identity(server)
    existing = next(
        (item for item in config.mcp_servers if connection_identity(item) == identity), None
    )
    if existing is None:
        return server, {}
    return None, {
        "ok": False,
        "metin": (
            f"Bu sunucu zaten '{existing.name}' adıyla ekli; ikinci kopya eklenmedi. "
            "Bağlantı çalışmıyorsa Bağlantılar ekranında 'Test et' ya da 'Bağlan' ile dene."
        ),
    }


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

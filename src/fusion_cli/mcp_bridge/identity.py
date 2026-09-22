"""İki MCP bağlantısının AYNI sunucuya gidip gitmediğini söyle.

Ölçüldü (17 Eylül denetimi): kullanıcının ayarında aynı Meta adresinin üç kopyası
vardı; her kopya ayrı bağlanıyor, araçlar üç kez kaydediliyor ve her tur üç kat
zaman aşımı yiyordu. Kopya; ad farklı olsa bile adres (ya da komut) aynı olan
bağlantıdır. Karşılaştırma yazım farklarına dayanıklı olmalı: `HTTPS://Mcp.X.com/mcp/`
ile `https://mcp.x.com/mcp` aynı sunucudur.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from ..config.models import HostedConnectorConfig, McpServerConfig, McpTransport

__all__ = [
    "connection_identity",
    "duplicate_of",
    "hosted_duplicate_of",
    "hosted_identity",
    "unique_configs",
    "unique_hosted_configs",
]

#: Şemanın varsayılan portu adreste yazılsa da yazılmasa da aynı sunucudur.
_DEFAULT_PORTS = {"http": 80, "https": 443}

#: npx'in "sormadan kur" bayrakları ve paket adındaki `@latest` eki bağlantının
#: kimliğini değiştirmez: `npx -y pkg` ile `npx pkg@latest` aynı sunucudur.
_INSTALL_FLAGS = frozenset({"-y", "--yes"})
_LATEST_SUFFIX = "@latest"


def _url_identity(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host if port in (None, _DEFAULT_PORTS.get(scheme)) else f"{host}:{port}"
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{netloc}{path}{query}"


def _command_identity(config: McpServerConfig) -> str:
    parts: list[str] = [config.command.strip()]
    for argument in config.args:
        if argument in _INSTALL_FLAGS:
            continue
        parts.append(argument.removesuffix(_LATEST_SUFFIX))
    return " ".join(parts)


def connection_identity(config: McpServerConfig) -> str:
    """Bağlantının gittiği sunucuyu temsil eden normalize anahtar."""
    if config.transport is McpTransport.STREAMABLE_HTTP:
        return f"http {_url_identity(config.url)}"
    return f"stdio {_command_identity(config)}"


def duplicate_of(configs: Iterable[McpServerConfig]) -> dict[str, str]:
    """Kopya bağlantı adı → aynı sunucuya giden İLK bağlantının adı.

    İlk kayıt kalır: kopyalar, bozuk bağlantının "eklendi" sanılıp yeniden
    eklenmesiyle oluştu (bkz. modül açıklaması); kullanıcının asıl kurduğu ve
    token'ı ona bağlı olan kayıt en eskisidir.
    """
    first_by_identity: dict[str, str] = {}
    duplicates: dict[str, str] = {}
    for config in configs:
        identity = connection_identity(config)
        original = first_by_identity.setdefault(identity, config.name)
        if original != config.name:
            duplicates[config.name] = original
    return duplicates


def unique_configs(configs: Iterable[McpServerConfig]) -> tuple[McpServerConfig, ...]:
    """Her sunucu için yalnız ilk bağlantıyı bırak (kopyalar bağlanmaz)."""
    items = tuple(configs)
    duplicates = duplicate_of(items)
    return tuple(config for config in items if config.name not in duplicates)


def hosted_identity(config: HostedConnectorConfig) -> str:
    """Barındırmalı connector'ın gittiği sunucuyu temsil eden normalize anahtar.

    Sağlayıcı ve hesap kimliğin parçasıdır: aynı MCP adresi ChatGPT oturumundan
    ve Claude oturumundan bağlanmışsa bunlar İKİ ayrı yetenektir, kopya değildir.
    """
    saglayici = config.provider.strip().lower()
    hesap = config.account.strip().lower()
    return f"{saglayici}/{hesap} {_url_identity(config.url)}"


def hosted_duplicate_of(configs: Iterable[HostedConnectorConfig]) -> dict[str, str]:
    """Kopya connector adı → aynı sunucuya giden İLK connector'ın adı.

    Ölçüldü (22 Eylül): kullanıcının gerçek ayarında aynı Meta Ads MCP adresi
    için iki kayıt vardı ("META ADS" ve "Meta Ads" — yalnız büyük/küçük harf
    farkı, ikisi de doğrulanmamış). `duplicate_of` yalnız `mcp_servers` yolunu
    koruyordu; barındırmalı connector'lar bu korumanın DIŞINDAYDI ve ikisi de
    kayıt defterine ekleniyordu.
    """
    first_by_identity: dict[str, str] = {}
    duplicates: dict[str, str] = {}
    for config in configs:
        identity = hosted_identity(config)
        original = first_by_identity.setdefault(identity, config.name)
        if original != config.name:
            duplicates[config.name] = original
    return duplicates


def unique_hosted_configs(
    configs: Iterable[HostedConnectorConfig],
) -> tuple[HostedConnectorConfig, ...]:
    """Her sunucu için yalnız ilk connector'ı bırak.

    Hangisinin kalacağı rastgele değil: doğrulanmış bir kayıt, doğrulanmamış
    kopyasına yenik düşmemeli. Aynı sunucuya giden kayıtlar arasında önce
    `verified` olanlar, sonra ayardaki sıra korunur.
    """
    items = tuple(configs)
    sirali = sorted(range(len(items)), key=lambda i: (not items[i].verified, i))
    duplicates = hosted_duplicate_of(items[i] for i in sirali)
    return tuple(config for config in items if config.name not in duplicates)

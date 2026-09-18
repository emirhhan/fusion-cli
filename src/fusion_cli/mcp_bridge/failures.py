"""MCP bağlantı başarısızlıklarını SINIFLANDIR ve her birine çözüm yaz.

Ölçüldü (17 Eylül denetimi): 401, var olmayan alan adı ve "giriş gerekli" üçü de
kullanıcıya aynı "MCP sunucusu başlatılamadı" cümlesiyle dönüyordu. Kullanıcı ne
olduğunu, neden olduğunu ve ne yapacağını bilemiyordu; bozuk bağlantılar bu yüzden
kaydedilip bırakılıyordu. Burada her başarısızlık tek bir türe indirgenir ve türün
mesajı eyleme dönüştürülebilir çözümü taşır (RULES.md "Hata Yönetimi").

Mesajlar mümkün olduğunca ARAYÜZDEKİ eylemi söyler ("Bağlan", "Test et",
"Kaldır"); terminal komutu yalnız eksik bir programın kurulumu gibi arayüzün
yapamayacağı işlerde önerilir.

Güvenlik: mesajlara komut ARGÜMANLARI ve sunucunun ham hata çıktısı girmez —
ikisi de sır taşıyabilir (PostgreSQL bağlantı adresi, token'lı URL).
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from urllib.parse import urlparse

import httpx
from mcp.client.auth.exceptions import OAuthRegistrationError
from mcp.shared.exceptions import McpError

from ..config.models import McpServerConfig, McpTransport
from .oauth import McpLoginRequiredError

__all__ = [
    "STATE_CONNECTED",
    "STATE_FAILED",
    "STATE_LOGIN_REQUIRED",
    "STATE_TIMEOUT",
    "McpFailure",
    "McpFailureKind",
    "classify_failure",
    "is_permanent_kind",
    "missing_command_failure",
]

#: Protokolde görünen bağlantı durumları (`durum` alanı).
STATE_CONNECTED = "bagli"
STATE_FAILED = "hata"
STATE_TIMEOUT = "zaman_asimi"
#: Sunucu çalışıyor ama kullanıcının girişini bekliyor. "hata" DEĞİLDİR: arayüz
#: bunu "Bağlan" düğmesiyle gösterir, turlar bu sunucuyu sessizce atlar.
STATE_LOGIN_REQUIRED = "giris_gerekli"

#: Stderr kuyruğunda paketin kayıt defterinde bulunmadığını gösteren izler.
#
# npm: `npm error code E404` / "is not in this registry" / ETARGET (sürüm yok).
# uv:  "not found in the package registry" / "No solution found when resolving".
# Ölçüldü (18 Eylül, npx -y @fusion-yok/paket): SDK yalnız "Connection closed"
# verir; türü ayırt etmenin tek yolu sürecin kendi çıktısıdır.
_PACKAGE_MISSING_MARKERS = (
    "e404",
    "is not in this registry",
    "etarget",
    "not found in the package registry",
    "no solution found when resolving",
)

#: Alan adı çözülemediğinde işletim sistemlerinin verdiği metinler.
_DNS_MARKERS = (
    "nodename nor servname",
    "name or service not known",
    "temporary failure in name resolution",
    "no address associated with hostname",
    "getaddrinfo failed",
)

#: Bilinen çalıştırıcılar → eksikse ne kurulmalı. Uygulama macOS'ta dağıtılıyor;
#: kurulum yolu Homebrew'dur.
_RUNNER_INSTALL_HINTS = {
    "uvx": "uv kurulu değil: Terminal'de `brew install uv` çalıştır",
    "uv": "uv kurulu değil: Terminal'de `brew install uv` çalıştır",
    "npx": "Node.js kurulu değil: Terminal'de `brew install node` çalıştır",
    "node": "Node.js kurulu değil: Terminal'de `brew install node` çalıştır",
    "docker": "Docker kurulu değil: Docker Desktop'ı kur ve aç",
}

#: Paketi hangi kayıt defterinde aradığımız (mesaj için).
_RUNNER_REGISTRIES = {"npx": "npm", "uvx": "PyPI"}

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_SERVER_ERROR = 500


class McpFailureKind(StrEnum):
    """Başarısızlık türü; protokolde `hata_turu` olarak taşınır."""

    UNAUTHORIZED = "yetkisiz"
    HOST_NOT_FOUND = "alan_adi_yok"
    NETWORK = "ag"
    ENDPOINT_NOT_FOUND = "adres_yok"
    SERVER_ERROR = "sunucu_hatasi"
    LOGIN_REQUIRED = "giris_gerekli"
    REGISTRATION_REJECTED = "kayit_reddi"
    COMMAND_MISSING = "komut_yok"
    PACKAGE_MISSING = "paket_yok"
    SERVER_EXITED = "surec_kapandi"
    CONFIGURATION = "yapilandirma"
    TIMEOUT = "zaman_asimi"
    UNKNOWN = "bilinmeyen"


#: Kendiliğinden düzelmeyen türler: kullanıcı bir şey değiştirmeden (komutu
#: kurmak, token'ı yenilemek, giriş yapmak) yeniden denemek aynı sonucu verir.
#: Havuz bunları oturum boyunca her turda yeniden denemez (bkz. `pool.py`).
_PERMANENT_KINDS = frozenset(
    {
        McpFailureKind.UNAUTHORIZED,
        McpFailureKind.HOST_NOT_FOUND,
        McpFailureKind.ENDPOINT_NOT_FOUND,
        McpFailureKind.LOGIN_REQUIRED,
        McpFailureKind.REGISTRATION_REJECTED,
        McpFailureKind.COMMAND_MISSING,
        McpFailureKind.PACKAGE_MISSING,
        McpFailureKind.CONFIGURATION,
    }
)


@dataclass(frozen=True, slots=True)
class McpFailure:
    """Sınıflandırılmış başarısızlık: tür + kullanıcıya gösterilecek çözüm."""

    kind: McpFailureKind
    message: str

    @property
    def state(self) -> str:
        if self.kind is McpFailureKind.LOGIN_REQUIRED:
            return STATE_LOGIN_REQUIRED
        if self.kind is McpFailureKind.TIMEOUT:
            return STATE_TIMEOUT
        return STATE_FAILED

    @property
    def is_permanent(self) -> bool:
        return self.kind in _PERMANENT_KINDS


def is_permanent_kind(kind: str | None) -> bool:
    """Protokoldeki `hata_turu` değeri kendiliğinden düzelmeyen bir tür mü?"""
    return kind in {item.value for item in _PERMANENT_KINDS}


def _leaf_errors(error: BaseException) -> Iterator[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        for inner in error.exceptions:
            yield from _leaf_errors(inner)
    else:
        yield error


def _error_chain(error: BaseException) -> Iterator[BaseException]:
    """Hatanın kendisi ve `__cause__`/`__context__` zinciri (döngüye karşı korumalı)."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _host(config: McpServerConfig) -> str:
    return urlparse(config.url).hostname or config.url


def _command_name(config: McpServerConfig) -> str:
    """Komutun yalnız ADI — argümanlar sır taşıyabileceği için mesaja girmez."""
    return PurePath(config.command).name or config.command


def missing_command_failure(command: str) -> McpFailure:
    """Çalıştırılacak program bulunamadı; bilinen çalıştırıcıda kurulumu söyle."""
    name = PurePath(command).name or command
    hint = _RUNNER_INSTALL_HINTS.get(name)
    if hint is not None:
        message = f"`{name}` bulunamadı. {hint}, sonra bağlantıyı yeniden ekle."
    else:
        message = (
            f"`{name}` komutu bulunamadı. Programın kurulu olduğunu ve adının doğru "
            "yazıldığını kontrol et, sonra bağlantıyı yeniden ekle."
        )
    return McpFailure(McpFailureKind.COMMAND_MISSING, message)


def _is_dns_failure(error: BaseException) -> bool:
    for link in _error_chain(error):
        if isinstance(link, socket.gaierror):
            return True
        text = str(link).lower()
        if any(marker in text for marker in _DNS_MARKERS):
            return True
    return False


def _http_status_failure(status: int, config: McpServerConfig) -> McpFailure:
    if status in (_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN):
        if config.token_env:
            reason = (
                "token geçersiz ya da süresi dolmuş"
                if status == _HTTP_UNAUTHORIZED
                else "token'ın bu sunucuya erişim yetkisi yok"
            )
            return McpFailure(
                McpFailureKind.UNAUTHORIZED,
                f"Sunucu erişim token'ını reddetti (HTTP {status}): {reason}. "
                "Bağlantıyı Kaldır ve yeni bir token'la yeniden ekle.",
            )
        return McpFailure(
            McpFailureKind.UNAUTHORIZED,
            f"Sunucu girişi reddetti (HTTP {status}). Bağlantılar ekranında 'Bağlan' "
            "ile yeniden giriş yap.",
        )
    if status >= _HTTP_SERVER_ERROR:
        return McpFailure(
            McpFailureKind.SERVER_ERROR,
            f"'{_host(config)}' sunucusu hata verdi (HTTP {status}). Sağlayıcı tarafında "
            "geçici bir sorun olabilir; biraz sonra 'Test et' ile yeniden dene.",
        )
    return _endpoint_not_found(config, status)


def _endpoint_not_found(config: McpServerConfig, status: int | None = None) -> McpFailure:
    code = f" (HTTP {status})" if status is not None else ""
    return McpFailure(
        McpFailureKind.ENDPOINT_NOT_FOUND,
        f"'{_host(config)}' adresinde MCP sunucusu bulunamadı{code}. Sağlayıcının "
        "belgelerindeki MCP adresini kontrol et; bağlantıyı Kaldır ve doğru adresle "
        "yeniden ekle.",
    )


def _package_missing(config: McpServerConfig) -> McpFailure:
    runner = _command_name(config)
    registry = _RUNNER_REGISTRIES.get(runner, "paket deposu")
    return McpFailure(
        McpFailureKind.PACKAGE_MISSING,
        f"Bu bağlantının paketi {registry} üzerinde bulunamadı ya da artık "
        "desteklenmiyor. Bağlantıyı Kaldır; katalogdaki güncel girişi kullan ya da "
        "paket adını düzeltip yeniden ekle.",
    )


def _classify_leaf(
    leaf: BaseException, config: McpServerConfig, stderr_tail: str
) -> McpFailure | None:
    """Tek bir hatayı sınıflandır; tanınmazsa None."""
    if isinstance(leaf, McpLoginRequiredError):
        return McpFailure(
            McpFailureKind.LOGIN_REQUIRED,
            "Bu bağlantı giriş istiyor. Bağlantılar ekranında 'Bağlan'a bas; giriş "
            "yapılana kadar turlarda atlanır.",
        )
    if isinstance(leaf, OAuthRegistrationError):
        return McpFailure(
            McpFailureKind.REGISTRATION_REJECTED,
            "Bu MCP sunucusu Fusion'ın kendini otomatik kaydetmesine izin vermiyor, bu "
            "yüzden giriş sayfası açılamadı. Sağlayıcının verdiği bir client_id ile "
            "bağlantıyı yeniden ekle.",
        )
    if isinstance(leaf, httpx.HTTPStatusError):
        return _http_status_failure(leaf.response.status_code, config)
    if isinstance(leaf, httpx.ConnectError | httpx.ConnectTimeout | socket.gaierror):
        if _is_dns_failure(leaf):
            return McpFailure(
                McpFailureKind.HOST_NOT_FOUND,
                f"'{_host(config)}' alan adı çözülemedi. Adreste yazım hatası olabilir "
                "ya da internet bağlantın kopuk; adresi kontrol et ve bağlantıyı doğru "
                "adresle yeniden ekle.",
            )
        return McpFailure(
            McpFailureKind.NETWORK,
            f"'{_host(config)}' sunucusuna ulaşılamadı. İnternet bağlantını kontrol et, "
            "sonra 'Test et' ile yeniden dene.",
        )
    if isinstance(leaf, FileNotFoundError) and config.transport is McpTransport.STDIO:
        return missing_command_failure(config.command)
    if isinstance(leaf, ValueError):
        # `transport.resolve_*` eksik sır/komut için zaten Türkçe ve eyleme
        # dönüştürülebilir mesaj üretir; değer İÇERMEZ, yalnız değişken adı taşır.
        return McpFailure(McpFailureKind.CONFIGURATION, str(leaf))
    if isinstance(leaf, TimeoutError):
        return McpFailure(
            McpFailureKind.TIMEOUT,
            "Sunucu zamanında yanıt vermedi. İlk çalıştırmada paket indiriliyor "
            "olabilir; biraz sonra 'Test et' ile yeniden dene.",
        )
    if isinstance(leaf, McpError):
        return _classify_closed_session(leaf, config, stderr_tail)
    return None


def _classify_closed_session(
    error: McpError, config: McpServerConfig, stderr_tail: str
) -> McpFailure | None:
    """SDK'nın "bağlantı kapandı" hatasını asıl nedenine indir."""
    text = str(error).lower()
    if config.transport is McpTransport.STREAMABLE_HTTP and "session terminated" in text:
        # SDK, `initialize` isteğine gelen 404'ü "Session terminated" olarak bildirir.
        return _endpoint_not_found(config, 404)
    if config.transport is not McpTransport.STDIO or "connection closed" not in text:
        return None
    tail = stderr_tail.lower()
    if any(marker in tail for marker in _PACKAGE_MISSING_MARKERS):
        return _package_missing(config)
    return McpFailure(
        McpFailureKind.SERVER_EXITED,
        f"`{_command_name(config)}` ile başlatılan sunucu süreci hemen kapandı. "
        "Bağlantının kurulum alanlarını (anahtar, klasör, adres) kontrol et, sonra "
        "'Test et' ile yeniden dene.",
    )


def classify_failure(
    error: BaseException, config: McpServerConfig, *, stderr_tail: str = ""
) -> McpFailure:
    """Bağlantı hatasını türüne ve çözümüne çevir.

    SDK asıl hatayı çoğu zaman `ExceptionGroup` içinde, yanında iptal ve "bağlantı
    kapandı" gibi sonuç hatalarıyla verir. Yapraklar sırayla denenir; en bilgilendirici
    olan (giriş, HTTP durumu, DNS…) genel olandan (zaman aşımı) önce gelir.
    """
    leaves = tuple(_leaf_errors(error))
    for generic_pass in (False, True):
        for leaf in leaves:
            if isinstance(leaf, TimeoutError | McpError) is not generic_pass:
                continue
            failure = _classify_leaf(leaf, config, stderr_tail)
            if failure is not None:
                return failure
    kind_name = type(leaves[0]).__name__ if leaves else type(error).__name__
    return McpFailure(
        McpFailureKind.UNKNOWN,
        f"MCP sunucusu başlatılamadı ({kind_name}). 'Test et' ile yeniden dene; "
        "sürerse bağlantıyı Kaldır ve yeniden ekle.",
    )

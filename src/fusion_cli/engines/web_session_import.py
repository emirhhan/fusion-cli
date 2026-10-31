"""Web MODEL oturumu → ajan tarayıcısı profili: tek yönlü, alan adı zorunlu kopya (P-023).

CLI (`fusion browser import-web-session`), REPL (`/oturum-aktar`) ve masaüstü RPC'si
(`tarayici.web_oturumu_aktar`) aynı akışı çağırır. Kurallar tek yerde:

- OTOMATİK paylaşım yoktur; kopyayı yalnız kullanıcı başlatır. Model oturumu değişmez.
- En az bir alan adı zorunludur ve iç ağ adı (`localhost`, özel IP, `.local`, tek etiketli
  ad) kabul edilmez. Profil yalnız bu alan adlarında çerez taşır (onay listesi).
- Kopya mevcut şifreli `BrowserProfileStore`'a yazılır; profili yükleyen her ajan çağrısı
  zaten `REMOTE_SESSION` onayından geçer (bkz. `tools/browser.py::browser_open_effect`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from ..config.browser_profiles import (
    SOURCE_WEB_SESSION,
    BrowserProfileStore,
    BrowserProfileSummary,
)
from ..core.cookie_files import (
    cookies_from_storage_state,
    domain_allowed,
    filter_by_domains,
    filter_origins_by_domains,
    internal_domain_reason,
    normalize_domain,
    origins_from_storage_state,
    validate_profile_name,
)
from ..core.errors import BrowserProfileError
from ..providers.web_session_export import (
    list_web_session_accounts,
    read_web_session_state,
    resolve_provider,
    web_session_domains,
    web_session_profile,
)

#: Profilden storage_state okuyan işlev; testler sahtesini verir.
StateReader = Callable[[Path], Awaitable[dict[str, object]]]

_NEED_DOMAIN = (
    "Model oturumundan aktarırken en az bir alan adı seç (-d chatgpt.com). Abonelik oturumunun "
    "tamamı ajan tarayıcısına taşınmaz."
)
_BLOCKED = "Bu alan adı aktarılamaz: {reason}"
_NO_KEY = (
    "Tarayıcı profili için şifreleme anahtarı yok: FUSION_SECRET_KEY tanımla ya da sistem "
    "anahtarlığını etkinleştir (fusion doctor)."
)
_NO_MATCH = "Seçilen alan adlarıyla eşleşen çerez yok; hiçbir şey yazılmadı."


@dataclass(frozen=True)
class WebSessionSource:
    """Diskteki bir web model oturumu: sağlayıcı, hesap, profil dizini."""

    provider: str
    account: str
    profile: Path


@dataclass(frozen=True)
class WebSessionPreview:
    """Onay ekranına giden özet: oturumdaki ve seçimle eşleşen alan adları; değer yok."""

    source: WebSessionSource
    domains: tuple[str, ...]
    matching: tuple[str, ...]


def available_web_sessions() -> tuple[WebSessionSource, ...]:
    return tuple(
        WebSessionSource(provider, account, web_session_profile(provider, account))
        for provider, account in list_web_session_accounts()
    )


def find_web_session(provider: str, account: str = "main") -> WebSessionSource:
    clean = resolve_provider(provider)
    name = account.strip() or "main"
    return WebSessionSource(clean, name, web_session_profile(clean, name))


def validate_domains(raw: tuple[str, ...] | None) -> tuple[str, ...]:
    """Alan adlarını normalize et; boşsa ya da iç ağ adı varsa anlaşılır hata."""
    cleaned = tuple(sorted({normalize_domain(item) for item in raw or () if item.strip()}))
    if not cleaned:
        raise BrowserProfileError(_NEED_DOMAIN)
    for domain in cleaned:
        reason = internal_domain_reason(domain)
        if reason is not None:
            raise BrowserProfileError(_BLOCKED.format(reason=reason))
    return cleaned


def preview_web_session(
    source: WebSessionSource, domains: tuple[str, ...] | None = None
) -> WebSessionPreview:
    """Alan adları şifre çözmeden okunur; `domains` verilirse eşleşenler ayrıca listelenir."""
    found = web_session_domains(source.profile)
    matching = tuple(item for item in found if domains and domain_allowed(item, domains))
    return WebSessionPreview(source, found, matching)


async def import_web_session(
    store: BrowserProfileStore,
    source: WebSessionSource,
    name: str,
    domains: tuple[str, ...] | None,
    *,
    reader: StateReader | None = None,
) -> BrowserProfileSummary:
    """Oturumu okuyup yalnız seçilen alan adlarıyla şifreli profile yaz."""
    allowed = validate_domains(domains)
    clean = validate_profile_name(name)
    if not store.available:
        # Chrome'a hiç bağlanmadan dur: okunan oturum yazılamayacaksa okunmaz.
        raise BrowserProfileError(_NO_KEY)
    state = await (reader or read_web_session_state)(source.profile)
    cookies = filter_by_domains(cookies_from_storage_state(state), allowed)
    origins = filter_origins_by_domains(origins_from_storage_state(state), allowed)
    if not cookies and not origins:
        raise BrowserProfileError(_NO_MATCH)
    # Şifreleme (scrypt + Fernet) bloklar: masaüstü olay döngüsünü tutmasın.
    return await asyncio.to_thread(
        store.save,
        clean,
        cookies,
        source=SOURCE_WEB_SESSION,
        allowed_domains=allowed,
        origins=origins,
    )

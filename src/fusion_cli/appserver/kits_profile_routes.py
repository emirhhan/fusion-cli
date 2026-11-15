"""Kit tarayıcısına Fusion profili: `tarayici.profil_tarif` + `tarayici.profil_disa_aktar` (P-023).

Kit'in kendi tarayıcısı (fusion-kits, Node/Playwright, ayrı süreç) şifreli `cookies.enc`'i
okuyamaz; ana anahtar Keychain'dedir ve Kit sürecine AÇILMAZ. Yol, Chrome köprüsüyle
(`kits_browser_routes.py`) aynı güven modelidir:

Kit (iframe) → Fusion hostu (`kitsProfileHost.ts`) → `tarayici.profil_tarif` (kapı ve kapsam;
kullanıcıya sorulmadan reddedilecekler burada döner) → onay penceresi (Kit adı, profil, alan
adları; HER istekte) → `tarayici.profil_disa_aktar` → `storage_state` yalnız o iframe'e,
bellek içi. Kits sunucusu onu kalıcı olmayan bir tarayıcı bağlamına verir; diske yazmaz.

Kapsam yalnız İSTENEN alan adlarıdır ve profilin onay listesiyle kesişir: profil
`example.com` için onaylıysa Kit `bank.com` isteyemez. İç ağ adları reddedilir. Bu modül
hiçbir şey loglamaz; tarif yanıtı ve hata metinleri çerez değeri taşımaz.

Kapatma: `runtime.disabled_tools` içine `fusion_profile` ya da `browser.profiles_enabled: false`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..config.browser_profiles import BrowserProfileStore, BrowserProfileSummary
from ..config.models import Config
from ..core.cookie_files import (
    cookies_from_storage_state,
    domain_allowed,
    filter_by_domains,
    filter_origins_by_domains,
    origins_from_storage_state,
    to_storage_state,
    validate_profile_name,
)
from ..core.errors import FusionError
from ..engines.web_session_import import validate_domains

KITS_PROFILE_DESCRIBE_ROUTE = "tarayici.profil_tarif"
KITS_PROFILE_EXPORT_ROUTE = "tarayici.profil_disa_aktar"
KITS_PROFILE_ROUTES = frozenset({KITS_PROFILE_DESCRIBE_ROUTE, KITS_PROFILE_EXPORT_ROUTE})
#: Kit'in Kits'te gördüğü araç adı; `runtime.disabled_tools` içine yazılınca yol kapanır.
KIT_PROFILE_TOOL = "fusion_profile"
#: Tek istekte en çok alan adı; daha geniş kapsam bir Kit işinin ihtiyacı değildir.
MAX_DOMAINS = 20
MAX_DOMAIN_CHARS = 253

_DISABLED = f"Kit'lere profil verme kapalı (runtime.disabled_tools içinde {KIT_PROFILE_TOOL})."
_PROFILES_OFF = "Tarayıcı profilleri kapalı (browser.profiles_enabled: false)."
_NO_KEY = "Şifreleme anahtarı yok: tarayıcı profilleri çözülemez."
_NEED_DOMAIN = "Kit hangi sitelerin oturumunu istediğini söylemeli (alan adı listesi boş)."
_TOO_MANY = f"En çok {MAX_DOMAINS} alan adı istenebilir."
_OUTSIDE = "Profil bu alan adları için onaylı değil: {domains}."
_NO_COOKIES = "Profilde istenen alan adlarına ait oturum yok."


@dataclass(frozen=True)
class _Scope:
    summary: BrowserProfileSummary
    #: İstenen ve profilin onayladığı alan adları (dışa verilecek kapsam).
    domains: tuple[str, ...]
    #: Profilde bu kapsamla eşleşen çerez alan adları (onay penceresinde gösterilir).
    matching: tuple[str, ...]


def _fail(status: str, text: str) -> dict[str, Any]:
    return {"ok": False, "status": status, "text": text}


def _requested(data: Mapping[str, object]) -> tuple[str, ...] | dict[str, Any]:
    raw = data.get("alanlar")
    if not isinstance(raw, list) or not raw:
        return _fail("failed", _NEED_DOMAIN)
    if len(raw) > MAX_DOMAINS:
        return _fail("failed", _TOO_MANY)
    if not all(isinstance(item, str) and len(item) <= MAX_DOMAIN_CHARS for item in raw):
        return _fail("failed", "Alan adı listesi geçersiz.")
    try:
        return validate_domains(tuple(raw), missing=_NEED_DOMAIN)
    except FusionError as error:
        return _fail("failed", str(error))


def _scope(
    store: BrowserProfileStore, config: Config, data: Mapping[str, object]
) -> _Scope | dict[str, Any]:
    """Kapıları uygula ve kapsamı çıkar; geçemezse hazır yanıt döndür."""
    if KIT_PROFILE_TOOL in config.runtime.disabled_tools:
        return _fail("denied", _DISABLED)
    if not config.browser.profiles_enabled:
        return _fail("denied", _PROFILES_OFF)
    if not store.available:
        return _fail("unavailable", _NO_KEY)
    requested = _requested(data)
    if isinstance(requested, dict):
        return requested
    try:
        summary = store.summary(validate_profile_name(str(data.get("ad") or "")))
    except FusionError as error:
        return _fail("failed", str(error))
    allowed = summary.allowed_domains
    outside = tuple(item for item in requested if allowed and not domain_allowed(item, allowed))
    if outside:
        return _fail("denied", _OUTSIDE.format(domains=", ".join(outside)))
    matching = tuple(item for item in summary.domains if domain_allowed(item, requested))
    if not matching:
        return _fail("failed", _NO_COOKIES)
    return _Scope(summary, requested, matching)


def describe_profile_export(
    store: BrowserProfileStore, config: Config, data: Mapping[str, object]
) -> dict[str, Any]:
    """Onay penceresi için `{ad, alan_adlari, profil_alanlari, kaynak}`; değer yok, damga yok."""
    scope = _scope(store, config, data)
    if isinstance(scope, dict):
        return scope
    return {
        "ok": True,
        "status": "ok",
        "ad": scope.summary.name,
        "alan_adlari": list(scope.domains),
        "profil_alanlari": list(scope.matching),
        "kaynak": scope.summary.source,
    }


def export_profile(
    store: BrowserProfileStore, config: Config, data: Mapping[str, object]
) -> dict[str, Any]:
    """Onaydan sonra: yalnız istenen alan adlarına süzülmüş `storage_state` (bellek içi)."""
    scope = _scope(store, config, data)
    if isinstance(scope, dict):
        return scope
    try:
        state = store.storage_state(scope.summary.name)
    except FusionError as error:
        return _fail("failed", str(error))
    cookies = filter_by_domains(cookies_from_storage_state(state), scope.domains)
    origins = filter_origins_by_domains(origins_from_storage_state(state), scope.domains)
    if not cookies and not origins:
        return _fail("failed", _NO_COOKIES)
    return {
        "ok": True,
        "status": "ok",
        "ad": scope.summary.name,
        "alan_adlari": list(scope.domains),
        "cerez_sayisi": len(cookies),
        "storage_state": to_storage_state(cookies, origins),
    }


def dispatch_kits_profile(
    name: str, store: BrowserProfileStore, config: Config, data: Mapping[str, object]
) -> dict[str, Any]:
    if name == KITS_PROFILE_EXPORT_ROUTE:
        return export_profile(store, config, data)
    return describe_profile_export(store, config, data)

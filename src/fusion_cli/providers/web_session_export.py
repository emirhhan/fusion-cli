"""Web MODEL oturumundan oturum okuma — yalnız kullanıcının başlattığı tek yönlü kopya (P-023).

`web_profiles/<sağlayıcı>/<hesap>/` ChatGPT/Claude/Gemini/Copilot abonelik oturumlarının
Chrome kullanıcı-veri dizinidir. Ajanın tarayıcısı bu dizini HİÇBİR ZAMAN kendiliğinden
kullanmaz: girişli bir abonelik çerezi, istem enjeksiyonlu bir sayfanın chatgpt.com'a
girişli istek yaptırmasına kapı açar. Bu modül yalnız `fusion browser import-web-session`,
REPL `/oturum-aktar` ya da masaüstü "Model oturumundan aktar" çağırınca çalışır.

Açık oturumu bozmamak için iki ayrı yol:

- Alan adı önizlemesi `Cookies` veritabanının GEÇİCİ KOPYASINDAN `host_key` okur; şifre
  çözmez, Chrome'a ve kilide dokunmaz.
- Değerler, web oturumunun KENDİ paylaşılan Chrome'undan CDP ile okunur
  (`SharedProfileBrowser`: süreçler arası kilit + kira). Chrome açıksa ona katılınır ve
  yalnız bu sürecin kirası bırakılır — sohbet sekmeleri kopmaz; kapalıysa görünmez açılır,
  okunur, son kiracı olarak kapatılır. Bu süreç zaten kiracıysa (masaüstü sekmesi web
  turu yürütüyor) kira BIRAKILMAZ. Giriş penceresi profili tutuyorsa anlaşılır hata döner.

Kodda doğrulandı (1 Kasım): açık bir profili ikinci kez başlatmak `clear_profile_singletons`
ile "Bu Fusion Chrome profili hâlâ açık" hatasına düşer; kalıcı bağlamı yeniden açmak yerine
çalışan Chrome'a CDP ile katılmak bu yüzden seçildi.
Çerez değerleri bu modülden yalnız `storage_state` sözlüğü içinde çıkar; loglanmaz.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from ..config.paths import web_profile_dir
from ..core.constants import MIN_BROWSER_TURN_S
from ..core.errors import BrowserProfileError
from .chrome_cookies import chrome_cookie_domains, list_chrome_profiles
from .web_browser import WEB_BROWSER_PROVIDERS, WebBrowserError, _shared_profile_browser
from .web_shared_browser import LEASE_DIR, SharedBrowserError, SharedProfileBrowser

# `Any`: Playwright nesneleri tembel yüklenir ve stub'ı yoktur.
SharedFactory = Callable[[Any, Path], SharedProfileBrowser]
PlaywrightFactory = Callable[[], AbstractAsyncContextManager[Any]]

_UNKNOWN_PROVIDER = "Bilinmeyen web sağlayıcısı: {raw}. Seçenekler: {names}"
_NO_PROFILE = (
    "{provider}/{account} web oturumu bu bilgisayarda yok. Önce `fusion web-login {provider}` "
    "ile giriş yap."
)
_BUSY = "Web oturumunun tarayıcısına bağlanılamadı: {error}"
_NO_PLAYWRIGHT = (
    "Playwright kurulu değil: `pip install -e '.[web]'` ve `python -m playwright install chromium`."
)


def resolve_provider(raw: str) -> str:
    """`chatgpt`, `chatgpt_web`, `Claude-Web` → kayıtlı sağlayıcı kimliği; yoksa hata."""
    clean = raw.strip().lower().replace("-", "_")
    candidate = clean if clean in WEB_BROWSER_PROVIDERS else f"{clean}_web"
    if candidate not in WEB_BROWSER_PROVIDERS:
        names = ", ".join(name.removesuffix("_web") for name in sorted(WEB_BROWSER_PROVIDERS))
        raise BrowserProfileError(_UNKNOWN_PROVIDER.format(raw=raw or "(boş)", names=names))
    return candidate


def web_session_profile(provider: str, account: str) -> Path:
    """Sağlayıcı hesabının profil dizini; diskte yoksa anlaşılır hata."""
    profile = web_profile_dir(provider, account)
    if not profile.is_dir():
        raise BrowserProfileError(_NO_PROFILE.format(provider=provider, account=account))
    return profile


def list_web_session_accounts() -> tuple[tuple[str, str], ...]:
    """Diskteki web oturumları: `(sağlayıcı, hesap)` çiftleri, sıralı."""
    found: list[tuple[str, str]] = []
    for provider in sorted(WEB_BROWSER_PROVIDERS):
        root = web_profile_dir(provider, "main").parent
        if not root.is_dir():
            continue
        found.extend((provider, item.name) for item in sorted(root.iterdir()) if item.is_dir())
    return tuple(found)


def web_session_domains(profile: Path) -> tuple[str, ...]:
    """Oturumdaki alan adları — `Cookies` kopyasından, şifre çözmeden, onay ekranı için."""
    domains: set[str] = set()
    for item in list_chrome_profiles(profile):
        domains.update(chrome_cookie_domains(item))
    return tuple(sorted(domains))


async def read_web_session_state(
    profile: Path,
    *,
    timeout_s: float = MIN_BROWSER_TURN_S,
    shared_factory: SharedFactory = _shared_profile_browser,
    playwright_factory: PlaywrightFactory | None = None,
) -> dict[str, object]:
    """Web oturumunun paylaşılan Chrome'undan `storage_state` oku (açık oturum bozulmaz)."""
    starter = playwright_factory or _default_playwright()
    async with starter() as playwright:
        shared = shared_factory(playwright, profile)
        # Bu süreç zaten kiracıysa (aynı süreçte web turu) kira bizim değildir: bırakılmaz.
        had_lease = (profile / LEASE_DIR / str(os.getpid())).exists()
        try:
            endpoint = await shared.acquire(headless=True, timeout_s=timeout_s)
        except (SharedBrowserError, WebBrowserError) as error:
            raise BrowserProfileError(_BUSY.format(error=error)) from error
        try:
            return await _storage_state(playwright, endpoint)
        finally:
            if not had_lease:
                await shared.release(force=False, timeout_s=timeout_s)


async def _storage_state(
    playwright: Any,  # noqa: ANN401 - Playwright tembel yüklenir, stub'ı yok
    endpoint: str,
) -> dict[str, object]:
    browser = await playwright.chromium.connect_over_cdp(endpoint)
    try:
        if not browser.contexts:
            return {"cookies": [], "origins": []}
        state = await browser.contexts[0].storage_state()
    finally:
        # CDP bağlantısını bırakır; Chrome'u kapatmak kira kaydının işidir.
        with contextlib.suppress(Exception):
            await browser.close()
    return state if isinstance(state, dict) else {"cookies": [], "origins": []}


def _default_playwright() -> PlaywrightFactory:
    try:
        # Playwright ağırdır ve yalnız bu açık istekte gerekir: tembel yüklenir.
        from playwright.async_api import async_playwright
    except ImportError as error:
        raise BrowserProfileError(_NO_PLAYWRIGHT) from error
    return async_playwright

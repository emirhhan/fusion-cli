"""Tarayıcı profiline GÖRÜNÜR pencerede giriş yapma (P-023).

`fusion browser login <profil> --url <adres>` ve masaüstündeki "Giriş penceresi aç":
profilin çerezleriyle görünür bir Chromium açılır, kullanıcı siteye kendisi girer,
pencereyi kapatınca tarayıcının güncel oturumu profile şifreli geri yazılır. Otomasyon
yok: Fusion bu pencerede tıklamaz, yazmaz, okumaz.

`python -m fusion_cli.providers.profile_login <profil> <adres>` kaynak kurulumda; paketli
ikilide `fusion browser login` (bkz. `web_control.login_argv` ile aynı gerekçe).
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from ..config.browser_profiles import (
    SOURCE_LOGIN,
    BrowserProfileStore,
    BrowserProfileSummary,
    default_browser_profile_store,
)
from ..core.cookie_files import cookies_from_storage_state, validate_profile_name
from ..core.errors import BrowserProfileError

#: Kullanıcının son sekmeyi kapatıp kapatmadığı bu aralıkla yoklanır (s).
_POLL_INTERVAL_S = 0.5
_INSTALL_HINT = (
    "Giriş penceresi için playwright gerekli: pip install 'fusion-cli[web]' && "
    "playwright install chromium"
)


def login_argv(name: str, url: str) -> list[str]:
    """Giriş penceresini açacak alt süreç komutu (paketli/kaynak kurulum ayrımıyla)."""
    clean = validate_profile_name(name)
    if getattr(sys, "frozen", False):
        return [sys.executable, "browser", "login", clean, "--url", url]
    return [sys.executable, "-m", "fusion_cli.providers.profile_login", clean, url]


async def open_profile_login(
    store: BrowserProfileStore, name: str, url: str
) -> BrowserProfileSummary:
    """Görünür tarayıcıyı aç, kullanıcı kapatana kadar bekle, oturumu profile yaz.

    Profil yoksa oluşturulur (kaynak `giris`, alan adı süzgeci yok); varsa onay listesi
    ve kaynağı korunarak çerezleri tazelenir.
    """
    clean = validate_profile_name(name)
    if not url.startswith(("http://", "https://")):
        raise BrowserProfileError("Giriş adresi http:// ya da https:// ile başlamalı.")
    try:
        from playwright.async_api import async_playwright
    except ImportError as error:
        raise BrowserProfileError(_INSTALL_HINT) from error

    # Depo düz sözlük verir; playwright `StorageState` TypedDict ister. Aynı biçimdir
    # (bkz. `cookie_files.to_storage_state`), sınır burada tek yerde geçilir.
    state: Any = store.storage_state(clean) if store.exists(clean) else None
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(headless=False)
        except Exception as error:
            raise BrowserProfileError(
                f"Giriş penceresi açılamadı ({type(error).__name__}). "
                "Tarayıcı ikilisi eksikse: playwright install chromium"
            ) from error
        context = (
            await browser.new_context(storage_state=state)
            if state is not None
            else await browser.new_context()
        )
        page = await context.new_page()
        await page.goto(url)
        while context.pages and browser.is_connected():  # noqa: ASYNC110 - kullanıcı bekleniyor
            await asyncio.sleep(_POLL_INTERVAL_S)
        if not browser.is_connected():
            raise BrowserProfileError(
                "Tarayıcı beklenmedik biçimde kapandı; oturum kaydedilmedi. Yeniden dene."
            )
        snapshot = await context.storage_state()
        await browser.close()
    cookies = cookies_from_storage_state(snapshot)
    if store.exists(clean):
        return store.update_cookies(clean, cookies)
    return store.save(clean, cookies, source=SOURCE_LOGIN)


def _main(argv: list[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write("kullanım: profile_login <profil> <adres>\n")
        return 2
    try:
        asyncio.run(open_profile_login(default_browser_profile_store(), argv[1], argv[2]))
    except BrowserProfileError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - alt süreç giriş noktası
    sys.exit(_main(sys.argv))

"""Tarayıcı profili içe aktarma akışları — CLI ve masaüstü RPC'nin ortak iş mantığı (P-023).

İki kaynak, tek sonuç: Netscape/JSON çerez dosyası ya da kullanıcının Chrome profili →
onaylı alan adlarıyla süzülmüş, şifreli bir `BrowserProfileStore` kaydı. Önizleme
fonksiyonları çerez DEĞERİ okumaz (dosyada okur ama dışarı yalnız alan adı/sayı verir;
Chrome'da hiç çözmez): onay ekranı Keychain'e dokunmadan "şu siteler aktarılacak" der.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config.browser_profiles import (
    SOURCE_CHROME,
    SOURCE_FILE,
    BrowserProfileStore,
    BrowserProfileSummary,
)
from ..core.cookie_files import Cookie, cookie_domains, filter_by_domains, parse_cookie_file
from ..core.errors import BrowserProfileError
from ..providers.chrome_cookies import (
    ChromeProfile,
    chrome_cookie_domains,
    list_chrome_profiles,
    read_chrome_cookies,
)

#: Tek seferde okunacak en büyük çerez dosyası; daha büyüğü dışa aktarma değildir.
MAX_COOKIE_FILE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class ImportPreview:
    """Onay ekranına giden özet: alan adları ve sayı, değer yok."""

    domains: tuple[str, ...]
    cookie_count: int
    source: str


def read_cookie_file(path: Path) -> tuple[Cookie, ...]:
    """Dosyayı oku ve çöz; yol, boyut ve biçim hataları tek tipte döner."""
    if not path.is_file():
        raise BrowserProfileError(f"Çerez dosyası bulunamadı: {path}")
    try:
        if path.stat().st_size > MAX_COOKIE_FILE_BYTES:
            raise BrowserProfileError(f"Çerez dosyası çok büyük (>8 MB): {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise BrowserProfileError(f"Çerez dosyası okunamadı: {error}") from error
    return parse_cookie_file(text, filename=path.name)


def preview_cookie_file(path: Path) -> ImportPreview:
    cookies = read_cookie_file(path)
    return ImportPreview(cookie_domains(cookies), len(cookies), SOURCE_FILE)


def import_cookie_file(
    store: BrowserProfileStore,
    path: Path,
    name: str,
    *,
    domains: tuple[str, ...] | None = None,
) -> BrowserProfileSummary:
    """Dosyayı profile yaz. `domains` verilirse yalnız onlar saklanır VE onay listesi olur."""
    cookies = filter_by_domains(read_cookie_file(path), domains)
    if not cookies:
        raise BrowserProfileError("Seçilen alan adlarıyla eşleşen çerez yok; hiçbir şey yazılmadı.")
    return store.save(name, cookies, source=SOURCE_FILE, allowed_domains=domains)


def find_chrome_profile(selector: str, chrome_dir: Path | None = None) -> ChromeProfile:
    """Dizin adı (`Default`, `Profile 1`) ya da görünen adla (`İş`) Chrome profili bul."""
    profiles = list_chrome_profiles(chrome_dir)
    if not profiles:
        raise BrowserProfileError(
            "Chrome profili bulunamadı: Chrome kurulu değil ya da hiç açılmamış"
            + (f" ({chrome_dir})" if chrome_dir else "")
            + "."
        )
    wanted = selector.strip().casefold()
    for profile in profiles:
        if wanted in (profile.directory.name.casefold(), profile.label.casefold()):
            return profile
    names = ", ".join(f"{item.label} ({item.directory.name})" for item in profiles)
    raise BrowserProfileError(f"'{selector}' adlı Chrome profili yok. Mevcutlar: {names}")


def preview_chrome_profile(profile: ChromeProfile) -> ImportPreview:
    """Alan adları şifre çözmeden okunur; Keychain diyaloğu bu adımda ÇIKMAZ."""
    domains = chrome_cookie_domains(profile)
    return ImportPreview(domains, len(domains), SOURCE_CHROME)


def import_chrome_profile(
    store: BrowserProfileStore,
    profile: ChromeProfile,
    name: str,
    *,
    domains: tuple[str, ...] | None = None,
) -> BrowserProfileSummary:
    """Chrome çerezlerini çözüp profile yaz (Keychain izni bu adımda istenir)."""
    cookies = read_chrome_cookies(profile, domains=domains)
    if not cookies:
        raise BrowserProfileError(
            "Seçilen alan adlarıyla eşleşen Chrome çerezi yok; hiçbir şey yazılmadı."
        )
    return store.save(name, cookies, source=SOURCE_CHROME, allowed_domains=domains)

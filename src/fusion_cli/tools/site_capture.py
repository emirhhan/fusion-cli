"""Site yakalama: sayfanın render edilmiş görünümünü yerel, betiksiz bir kopyaya çevir.

Ölçüldü (3 Ekim 2026, kopyalama deneyi): sneaksup.com Next.js + MUI/emotion ile
yazılmış; emotion stil kurallarını çalışma anında CSSOM'a ekliyor. `page.content()`
ve ağdan inen CSS dosyaları bu kuralları taşımadığı için eski ayna "çıplak"
çıkıyordu. CSSOM'u (`document.styleSheets[*].cssRules`) döküp betikleri sökerek
JS kapalı açılan kopya, ana sayfayı görsel olarak neredeyse birebir verdi.

Bu modül o yöntemin ürünleşmiş hali ve şunları ekler:
- Varlıklar (görsel, yazı tipi, CSS `url()`) İNDİRİLİR ve yerel yola çevrilir;
  kopya kaynağa hotlink yapmaz.
- Sayfa başlık / gövde / altlık parçalarına bölünür (tema iskeleti bunları kullanır).
- Kaydırma ile tembel görseller yüklenir.

Sınır: sunucu davranışı (sepet, ödeme, arama) kopyalanmaz — o iş WooCommerce'in.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import mimetypes
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page

from .mirror import MAX_ASSET_BYTES, asset_local_path, is_mirrorable

CAPTURE_SCRIPT = Path(__file__).with_name("assets") / "capture_page.js"
#: Referans ekran görüntülerinin genişlikleri: masaüstü ve telefon.
VIEWPORTS = ((1440, 900), (390, 844))
NAVIGATION_TIMEOUT_MS = 60_000
#: Tembel görsellerin yüklenmesi için kaydırma adımı ve en fazla derinlik (piksel).
SCROLL_STEP_PX = 900
SCROLL_MAX_PX = 15_000
SCROLL_PAUSE_MS = 250
SETTLE_MS = 2_500
#: Yakalamada indirilecek en fazla varlık. Ölçüldü (sneaksup): ana sayfada 485
#: görünür görsel vardı; aynanın 400 sınırı görsellerin dörtte birini kırık bıraktı.
CAPTURE_MAX_ASSETS = 1_500
#: Eşzamanlı indirme sayısı (kaynak siteye nazik, yine de dakikalarca sürmesin).
DOWNLOAD_CONCURRENCY = 8
#: Video dosyaları (hero videosu) için ayrı boyut sınırı.
MAX_VIDEO_BYTES = 30 * 1024 * 1024
_VIDEO_SUFFIXES = (".mp4", ".webm")
#: CSS `url(...)` başvuruları (data: ve # hariç).
_CSS_URL = re.compile(r"url\(\s*(['\"]?)(?!data:|#)([^'\")]+)\1\s*\)")
#: HTML içindeki src / srcset / poster / satır içi stil adresleri.
_HTML_URL = re.compile(r"(?:src|poster)=\"(https?://[^\"]+)\"|url\(&quot;(https?://[^&]+)&quot;\)")
_SRCSET = re.compile(r"srcset=\"([^\"]+)\"")


class CaptureError(RuntimeError):
    """Yakalama yapılamadı (Playwright yok ya da sayfa açılmadı)."""


@dataclass(frozen=True, slots=True)
class CapturedPage:
    """Bir sayfanın yakalanmış parçaları (varlık adresleri henüz uzak)."""

    url: str
    title: str
    lang: str
    body_class: str
    header: str
    main: str
    footer: str
    #: Sabit/mutlak başlığın kapladığı yükseklik (piksel); akışta ise 0.
    header_offset: int = 0
    screenshots: dict[int, bytes] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SiteCapture:
    """Bütün sayfalar + birleşik CSS + indirilen varlıklar (uzak → yerel yol)."""

    pages: tuple[CapturedPage, ...]
    css: str
    assets: dict[str, str]
    problems: tuple[str, ...] = ()


def css_urls(css: str, base: str) -> list[str]:
    """CSS içindeki `url()` adreslerini mutlak hale getirip sırayla döndür."""
    return [urljoin(base, match.group(2).strip()) for match in _CSS_URL.finditer(css)]


def absolutize_css(css: str, base: str) -> str:
    """Göreli `url()` adreslerini CSS dosyasının kendi adresine göre mutlaklaştır."""
    return _CSS_URL.sub(lambda m: f"url({urljoin(base, m.group(2).strip())})", css)


def _largest_candidate(srcset: str) -> str:
    """srcset'in son (en büyük) adayı; diğer boyutlar indirilmez."""
    adaylar = [part.strip().split(" ", 1)[0] for part in srcset.split(",") if part.strip()]
    return adaylar[-1] if adaylar else ""


def html_urls(html: str) -> list[str]:
    """HTML parçasındaki indirilecek görsel/video adresleri."""
    bulunan = [m.group(1) or m.group(2) for m in _HTML_URL.finditer(html)]
    bulunan.extend(_largest_candidate(match.group(1)) for match in _SRCSET.finditer(html))
    return [url for url in bulunan if url.startswith(("http://", "https://"))]


def collapse_srcset(html: str) -> str:
    """srcset'i en büyük tek adaya indir: yalnız o indirildiği için diğerleri hotlink olurdu."""
    return _SRCSET.sub(lambda m: f'srcset="{_largest_candidate(m.group(1))}"', html)


def drop_remote_srcset(html: str) -> str:
    """Yerelleşmemiş (hâlâ uzak) srcset'i sil; tarayıcı yerel `src`'e düşer."""
    return _SRCSET.sub(lambda m: "" if "://" in m.group(1) else m.group(0), html)


def localize(text: str, assets: dict[str, str], prefix: str) -> str:
    """Uzak adresleri `prefix + yerel yol` ile değiştir; yalnız TAM adres eşleşir.

    Adresin ardından tırnak, boşluk, parantez ya da virgül gelmeli: `a.css`
    eşlemesi `a.css.map` adresinin önekini bozmasın (testle ölçüldü).
    """
    if not assets:
        return text
    desen = re.compile(
        "("
        + "|".join(re.escape(u) for u in sorted(assets, key=len, reverse=True))
        + ")"
        + r"(?=[\"'\s),]|$)"
    )
    return desen.sub(lambda m: f"{prefix}{assets[m.group(1)]}", text)


def same_site_paths(html: str, source: str) -> str:
    """Kaynak alan adına giden bağlantıları köke göreli yola çevir (gezinti yerel kalsın)."""
    kok = f"{urlparse(source).scheme}://{urlparse(source).netloc}"
    return html.replace(f'href="{kok}/', 'href="/').replace(f'href="{kok}"', 'href="/"')


async def _scroll(page: Page) -> None:
    for y in range(0, SCROLL_MAX_PX, SCROLL_STEP_PX):
        await page.evaluate(f"window.scrollTo(0, {y})")
        await page.wait_for_timeout(SCROLL_PAUSE_MS)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(SETTLE_MS)


async def _capture_one(
    browser: Browser, url: str, script: str
) -> tuple[CapturedPage, str, list[str]]:
    shots: dict[int, bytes] = {}
    veri: dict[str, Any] = {}
    for genislik, yukseklik in VIEWPORTS:
        context = await browser.new_context(viewport={"width": genislik, "height": yukseklik})
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            await page.wait_for_timeout(SETTLE_MS)
            await _scroll(page)
            shots[genislik] = await page.screenshot(full_page=True, type="jpeg", quality=60)
            if not veri:
                veri = await page.evaluate(script)
        finally:
            await context.close()
    sayfa = CapturedPage(
        url=url,
        title=str(veri.get("title", "")),
        lang=str(veri.get("lang", "")),
        body_class=str(veri.get("bodyClass", "")),
        header=str(veri.get("header", "")),
        main=str(veri.get("main", "")),
        footer=str(veri.get("footer", "")),
        header_offset=int(veri.get("headerOffset") or 0),
        screenshots=shots,
    )
    return sayfa, str(veri.get("css", "")), [str(href) for href in veri.get("blocked", [])]


async def _blocked_css(browser: Browser, hrefs: list[str], problems: list[str]) -> list[str]:
    """Çapraz kökenli (CSSOM'dan okunamayan) stil dosyalarını indir."""
    istek = await browser.new_context()
    metinler = []
    try:
        for href in dict.fromkeys(hrefs):
            yanit = await istek.request.get(href, timeout=NAVIGATION_TIMEOUT_MS)
            if yanit.ok:
                metinler.append(absolutize_css(await yanit.text(), href))
            else:
                problems.append(f"stil dosyası indirilemedi ({yanit.status}): {href}")
    finally:
        await istek.close()
    return metinler


def _with_suffix(local: str, content_type: str) -> str:
    """Uzantısız yerel yola içerik türünden uzantı ekle (`/_next/image?…` gibi adresler).

    php -S uzantısız dosyayı application/octet-stream ile sunar; görsel yine de
    çoğu tarayıcıda açılır ama CSS arka planı ve video açılmayabilir.
    """
    if "." in local.rsplit("/", 1)[-1]:
        return local
    uzanti = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ""
    return local + uzanti


def _wanted(url: str) -> bool:
    yol = urlparse(url).path.lower()
    return is_mirrorable(url) or "/image" in yol or yol.endswith(_VIDEO_SUFFIXES)


async def _download(
    browser: Browser, urls: list[str], folder: Path, problems: list[str]
) -> dict[str, str]:
    """Varlıkları paralel indir; uzak adres → yerel yol (folder'a göre) eşlemesi döner."""
    istenen = list(dict.fromkeys(u for u in urls if _wanted(u)))
    if len(istenen) > CAPTURE_MAX_ASSETS:
        problems.append(f"{len(istenen)} varlıktan ilk {CAPTURE_MAX_ASSETS} tanesi indirildi")
    from playwright.async_api import Error as PlaywrightError  # tembel: opsiyonel ekstra

    istek = await browser.new_context()
    sinir = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    eslesme: dict[str, str] = {}

    async def _bir(url: str) -> None:
        async with sinir:
            try:
                # HTML özniteliğindeki adres kaçışlı (`&amp;`); istek gerçek adresle,
                # eşleme ise sayfada geçen biçimle yapılır ki yerine konabilsin.
                yanit = await istek.request.get(
                    html_lib.unescape(url), timeout=NAVIGATION_TIMEOUT_MS
                )
                govde = await yanit.body() if yanit.ok else b""
                tur = yanit.headers.get("content-type", "")
            except PlaywrightError:
                # Tek varlığın ağ hatası yakalamayı düşürmez; eksik görsel denetimde görünür.
                return
        tavan = (
            MAX_VIDEO_BYTES
            if urlparse(url).path.lower().endswith(_VIDEO_SUFFIXES)
            else MAX_ASSET_BYTES
        )
        if not govde or len(govde) > tavan:
            return
        yerel = _with_suffix(asset_local_path(url), tur)
        hedef = folder / yerel
        await asyncio.to_thread(hedef.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(hedef.write_bytes, govde)
        eslesme[url] = yerel

    try:
        await asyncio.gather(*(_bir(url) for url in istenen[:CAPTURE_MAX_ASSETS]))
    finally:
        await istek.close()
    return eslesme


async def capture_site(urls: list[str], folder: Path) -> SiteCapture:
    """Sayfaları yakala, varlıkları `folder` altına indir. Playwright gerekir."""
    try:
        from playwright.async_api import async_playwright  # tembel: opsiyonel ekstra
    except ImportError as error:
        raise CaptureError("Playwright kurulu değil: `pip install playwright`") from error
    script = CAPTURE_SCRIPT.read_text(encoding="utf-8")
    problems: list[str] = []
    async with async_playwright() as oynatici:
        browser = await oynatici.chromium.launch()
        try:
            sayfalar, css_parcalari, engelli = [], [], []
            for url in urls:
                sayfa, css, blocked = await _capture_one(browser, url, script)
                sayfa = replace(
                    sayfa,
                    header=collapse_srcset(sayfa.header),
                    main=collapse_srcset(sayfa.main),
                    footer=collapse_srcset(sayfa.footer),
                )
                sayfalar.append(sayfa)
                css_parcalari.append(absolutize_css(css, url))
                engelli.extend(blocked)
            css_parcalari = [*await _blocked_css(browser, engelli, problems), *css_parcalari]
            css = "\n".join(dict.fromkeys(css_parcalari))
            # Sıra önceliktir (MAX_ASSETS sınırı): önce sayfada GÖRÜNEN görseller, sonra
            # CSS başvuruları. Ölçüldü: sneaksup CSS'i 900+ yazı tipi/ikon varyantı
            # anıyordu ve ilk 400 hakkı bunlara gidip ürün görselleri inmiyordu.
            adresler = [
                url
                for sayfa in sayfalar
                for url in html_urls(sayfa.header + sayfa.main + sayfa.footer)
            ]
            adresler.extend(css_urls(css, urls[0]))
            varliklar = await _download(browser, adresler, folder, problems)
        finally:
            await browser.close()
    return SiteCapture(tuple(sayfalar), css, varliklar, tuple(problems))

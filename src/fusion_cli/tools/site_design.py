"""Bir sitenin TASARIM SİSTEMİNİ ölç ve varlıklarını projeye indir (`site_design`).

Ölçüldü (2 Ekim 2026, "sneaksup" testi): kullanıcı bir siteye "görsellerinden
yazılarına, yazı tiplerinden bileşenlerine kadar" benzeyen bir site istedi. Fusion
sayfayı yalnız METİN olarak okuyabiliyordu (`browser_open`, `chrome_page`); yazı
tipini, renkleri, ölçüleri ve kart yapısını TAHMİN ediyordu ve sonuç benzemiyordu.

Bu araç her sayfada aynı ölçüm kodunu (`assets/design_probe.js`) çalıştırır:

- Fusion Browser eklentisi bağlıysa KULLANICININ Chrome'unda (girişli oturum,
  gerçek tarayıcı), değilse başsız Chromium'da (Playwright).
- Ana sayfadan başlayıp menü/kategori, ürün ve sepet sayfalarını kendisi bulur.
- Görselleri ve yazı tipi dosyalarını projeye indirir, ölçüleri `tasarim.json`'a yazar.

Telif notu araç çıktısında modele söylenir: indirilenler yerel çalışma içindir;
yayında logo ve ürün görselleri değiştirilmelidir.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ..core.tools import ChromeControl

PROBE_SOURCE = Path(__file__).parent / "assets" / "design_probe.js"
#: Ölçüm ve indirilen varlıkların varsayılan klasörü (proje kökünde).
DEFAULT_FOLDER = "tasarim-kaynak"
#: Bir çağrıda ölçülecek en fazla sayfa (ana, 2 kategori, ürün, sepet + istenenler).
MAX_PAGES = 6
#: İndirilecek en fazla görsel ve tek dosya üst sınırı. Ölçüldü (sneaksup.com, 5 sayfa):
#: 60 görsel 5,5 MB tuttu; ürün görselleri (≤48) + bölüm görselleri + logo için 120.
MAX_IMAGE_DOWNLOADS = 120
MAX_ASSET_BYTES = 6 * 1024 * 1024
MAX_FONT_DOWNLOADS = 16
#: Kahraman/afiş videosu: sayfanın ilk izlenimi odur, ama dosya büyüktür. En fazla iki
#: video, her biri bu sınıra kadar indirilir; aşan video için posteri/ekran görüntüsü kalır.
MAX_VIDEO_DOWNLOADS = 2
MAX_VIDEO_BYTES = 30 * 1024 * 1024
#: `urunler.json`'a yazılacak en fazla ürün (sayfa başına ölçüm sınırı 24).
MAX_PRODUCTS = 48
#: Sayfa yükleme süresi; tembel görseller için kaydırma sonrası bekleme.
PAGE_TIMEOUT_MS = 30_000
SCROLL_SETTLE_MS = 1200
VIEWPORT = {"width": 1440, "height": 900}
_FONT_SUFFIXES = (".woff2", ".woff", ".ttf", ".otf")
_SCROLL_THROUGH = (
    "async () => { for (let y = 0; y < document.body.scrollHeight; y += 700) { "
    "window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); } "
    "window.scrollTo(0, 0); }"
)
#: Ekran görüntüsünü kapatan çerez/izin afişini gizle (yalnız başsız tarayıcıda; kullanıcının
#: kendi Chrome'unda sayfaya dokunulmaz). Ölçüldü: afiş her ekran görüntüsünün alt 120 px'ini
#: kapatıyordu ve ilk ürün şeridi görünmüyordu.
_HIDE_CONSENT = (
    "() => { for (const el of document.querySelectorAll('body *')) { "
    "const cs = getComputedStyle(el); "
    "if ((cs.position === 'fixed' || cs.position === 'sticky') && "
    "/çerez|cookie|consent/i.test(el.innerText || '') && "
    "el.getBoundingClientRect().top > innerHeight * 0.4) el.style.display = 'none'; } }"
)
_CART = re.compile(r"sepet|cart|basket|\bbag\b|alışveriş çantası", re.IGNORECASE)
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Fusion site_design"


class DesignError(RuntimeError):
    """Ölçüm yapılamadı; mesaj modele olduğu gibi gider."""


@dataclass
class DesignReport:
    pages: list[dict[str, Any]] = field(default_factory=list)
    screenshots: list[Path] = field(default_factory=list)
    images: dict[str, str] = field(default_factory=dict)
    fonts: dict[str, str] = field(default_factory=dict)
    videos: dict[str, str] = field(default_factory=dict)
    source: str = ""


def probe_script() -> str:
    """Playwright'ta çalışan ölçüm fonksiyonu (eklentideki ile birebir aynı kod)."""
    govde = PROBE_SOURCE.read_text(encoding="utf-8")
    return f"(limits) => {{\n{govde}\n  return designProbe(limits || {{}});\n}}"


async def measure(
    url: str, *, chrome: ChromeControl | None, extra_pages: tuple[str, ...] = ()
) -> DesignReport:
    """Ana sayfayı ve keşfedilen sayfaları ölç."""
    if chrome is not None:
        try:
            return await _measure_chrome(chrome, url, extra_pages)
        except (ConnectionError, TimeoutError, DesignError):
            pass  # Eklenti yanıt vermiyorsa başsız tarayıcıyla sürer.
    return await _measure_playwright(url, extra_pages)


def discover_pages(home: dict[str, Any], extra: tuple[str, ...]) -> list[str]:
    """Ana sayfa ölçümünden incelenecek sayfaları seç: menü, ürün, sepet."""
    home_url = str(home.get("url", ""))
    host = urlparse(home_url).netloc

    def same(href: str) -> bool:
        return urlparse(href).netloc == host and href.rstrip("/") != home_url.rstrip("/")

    navigation = home.get("navigation", {})
    menu_links = [link for link in navigation.get("menu", []) if same(link.get("href", ""))]
    menu = [link["href"] for link in menu_links]
    pages: list[str] = [*extra, *menu[:2]]
    product = next(
        (c["link"] for c in home.get("components", []) if c.get("link") and same(c["link"])), None
    )
    if product:
        pages.append(product)
    candidates = [*menu_links, *navigation.get("header", []), *navigation.get("footer", [])]
    cart = next(
        (
            link["href"]
            for link in candidates
            if same(link.get("href", ""))
            and (_CART.search(link.get("href", "")) or _CART.search(link.get("text", "")))
        ),
        None,
    )
    if cart:
        pages.append(cart)
    return list(dict.fromkeys(pages))[: MAX_PAGES - 1]


async def _measure_playwright(url: str, extra: tuple[str, ...]) -> DesignReport:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise DesignError(
            "Tarayıcı yok: Fusion Browser eklentisi bağlı değil ve Playwright kurulu değil."
        ) from exc
    report = DesignReport(source="başsız Chromium")
    script = probe_script()
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        try:
            page = await browser.new_page(viewport=VIEWPORT, user_agent=_USER_AGENT)  # type: ignore[arg-type]
            home = await _playwright_page(page, url, script, report)
            for target in discover_pages(home, extra):
                with contextlib.suppress(Exception):
                    await _playwright_page(page, target, script, report)
        finally:
            await browser.close()
    return report


async def _playwright_page(
    page: Any, url: str, script: str, report: DesignReport
) -> dict[str, Any]:
    await page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
    with contextlib.suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=8000)
    # Tembel yüklenen görseller için sayfayı sonuna kadar kaydır, sonra başa dön.
    await page.evaluate(_SCROLL_THROUGH)
    await page.wait_for_timeout(SCROLL_SETTLE_MS)
    with contextlib.suppress(Exception):
        await page.evaluate(_HIDE_CONSENT)
    data: dict[str, Any] = await page.evaluate(script, {})
    report.pages.append(data)
    report.screenshots.append(Path(f"ekran-{len(report.pages)}.jpg"))
    shot = await page.screenshot(type="jpeg", quality=70, full_page=False)
    report.pages[-1]["_screenshot_bytes"] = shot
    return data


async def _measure_chrome(chrome: ChromeControl, url: str, extra: tuple[str, ...]) -> DesignReport:
    report = DesignReport(source="Fusion Browser (kullanıcının Chrome'u)")
    home = await _chrome_page(chrome, url, report, first=True)
    for target in discover_pages(home, extra):
        with contextlib.suppress(ConnectionError, TimeoutError, DesignError):
            await _chrome_page(chrome, target, report, first=False)
    return report


async def _chrome_page(
    chrome: ChromeControl, url: str, report: DesignReport, *, first: bool
) -> dict[str, Any]:
    moved = await chrome.invoke("navigate", {"url": url})
    if not moved.get("ok") and first:
        moved = await chrome.invoke("tab_open", {"url": url})
    if not moved.get("ok"):
        raise DesignError(str(moved.get("hata") or "Sekme açılamadı."))
    await asyncio.sleep(SCROLL_SETTLE_MS / 1000)
    result = await chrome.invoke("design", {})
    if not result.get("ok") or not isinstance(result.get("veri"), dict):
        raise DesignError(str(result.get("hata") or "Ölçüm yapılamadı (eklenti güncel mi?)."))
    data: dict[str, Any] = result["veri"]
    shot = await chrome.invoke("screenshot", {})
    image = (shot.get("veri") or {}).get("image") if shot.get("ok") else None
    if isinstance(image, str) and "," in image:
        data["_screenshot_bytes"] = base64.b64decode(image.partition(",")[2])
    report.pages.append(data)
    return data


async def download_assets(report: DesignReport, folder: Path) -> None:
    """Görselleri, yazı tiplerini ve kahraman videolarını indir.

    Görsel sırası önemlidir (sınır dolarsa sondakiler düşer): logo, bölüm görselleri,
    ürün görselleri, sonra gösterilen alana göre kalanlar.
    """
    fonts = [
        source
        for page in report.pages
        for face in page.get("fonts", {}).get("faces", [])
        for source in face.get("sources", [])
        if urlparse(source).path.lower().endswith(_FONT_SUFFIXES)
    ]
    videos = [
        section["video"]["src"]
        for page in report.pages
        for section in page.get("sections", [])
        if (section.get("video") or {}).get("src", "").startswith("http")
    ]
    report.images = await _fetch_all(
        _unique(_image_queue(report))[:MAX_IMAGE_DOWNLOADS], folder / "images", MAX_ASSET_BYTES
    )
    report.fonts = await _fetch_all(
        _unique(fonts)[:MAX_FONT_DOWNLOADS], folder / "fonts", MAX_ASSET_BYTES
    )
    report.videos = await _fetch_all(
        _unique(videos)[:MAX_VIDEO_DOWNLOADS], folder / "video", MAX_VIDEO_BYTES
    )


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item.startswith("http")))


def _image_queue(report: DesignReport) -> list[str]:
    logos = [str(page.get("logo", "")) for page in report.pages]
    sectional: list[str] = []
    for page in report.pages:
        for section in page.get("sections", []):
            video = section.get("video") or {}
            sectional.extend(
                [section.get("backgroundImage", ""), video.get("poster", ""), *section["images"]]
            )
    products = [item["image"] for page in report.pages for item in page.get("products", [])]
    galleries = [
        src for page in report.pages for src in (page.get("product") or {}).get("images", [])
    ]
    rest: list[str] = []
    for page in report.pages:
        ranked = sorted(page.get("images", []), key=lambda i: -(i["shown"][0] * i["shown"][1]))
        rest.extend(item["src"] for item in ranked)
    return [*logos, *sectional, *products, *galleries, *rest]


def collect_products(report: DesignReport, folder_label: str) -> list[dict[str, Any]]:
    """Ölçülen sayfalardaki ürünler: ad, fiyat, yerel görsel, kategori (+ayrıntı sayfası)."""

    def local(url: str) -> str:
        name = report.images.get(url)
        return f"{folder_label}/images/{name}" if name else ""

    # Sayfalar SIRAYLA birer ürün verir: sınır dolduğunda tek sayfanın (ana sayfa) ürünleri
    # listeyi kaplamasın, her kategori temsil edilsin. Kategori sayfaları önce gelir ki
    # ana sayfada da görünen ürün kategorisini alsın.
    pages = sorted(report.pages, key=lambda page: not _category(str(page.get("url", ""))))
    queues = [
        [(item, _category(str(page.get("url", "")))) for item in page.get("products", [])]
        for page in pages
    ]
    products: dict[str, dict[str, Any]] = {}
    for row in zip_longest(*queues):
        for entry in row:
            if entry is None or len(products) >= MAX_PRODUCTS:
                continue
            item, category = entry
            link = str(item.get("link", ""))
            if not link or not item.get("name") or link in products:
                continue
            amount, currency = parse_price(str(item.get("price", "")))
            products[link] = {
                "ad": item["name"],
                "fiyat": item.get("price", ""),
                "fiyat_sayi": amount,
                "para_birimi": currency,
                "gorsel": local(str(item.get("image", ""))),
                "kategori": category,
                "kaynak": link,
            }
    for page in report.pages:
        detail = page.get("product")
        if not detail:
            continue
        entry = products.setdefault(
            str(page.get("url", "")),
            {"ad": detail.get("name", ""), "kategori": "", "kaynak": page.get("url", "")},
        )
        entry["fiyat"] = entry.get("fiyat") or detail.get("price", "")
        if entry.get("fiyat_sayi") is None:
            entry["fiyat_sayi"], entry["para_birimi"] = parse_price(str(entry["fiyat"]))
        entry["galeri"] = [path for src in detail.get("images", []) if (path := local(src))]
        entry["gorsel"] = entry.get("gorsel") or next(iter(entry["galeri"]), "")
        entry["secenekler"] = list(dict.fromkeys(detail.get("options", [])))
        entry["aciklama"] = detail.get("description", "")
    return list(products.values())


_PRICE_NUMBER = re.compile(r"\d[\d.,]*")
_CURRENCIES = (
    ("₺", "TRY"),
    ("TL", "TRY"),
    ("TRY", "TRY"),
    ("€", "EUR"),
    ("$", "USD"),
    ("£", "GBP"),
)


def parse_price(text: str) -> tuple[float | None, str]:
    """'3.899,00 TL' → (3899.0, 'TRY'). Ölçüldü (10. kabul koşusu): model bunu 389900 okudu
    ve mağazayı dolar bıraktı; sayı ve birim burada bir kez doğru çözülür."""
    match = _PRICE_NUMBER.search(text or "")
    currency = next((code for sign, code in _CURRENCIES if sign in (text or "")), "")
    if match is None:
        return None, currency
    raw = match.group(0)
    if "," in raw and "." in raw:
        # Son ayraç ondalıktır: 3.899,00 → 3899.00 ; 3,899.00 → 3899.00
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        raw = raw.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in raw:
        # Tek virgül: iki haneli kuyruk ondalık (7.999,00 biçimi), üç haneli binlik ayracı.
        head, _, tail = raw.rpartition(",")
        raw = f"{head}.{tail}" if len(tail) <= 2 else head + tail
    elif raw.count(".") > 1 or (raw.count(".") == 1 and len(raw.rpartition(".")[2]) == 3):
        raw = raw.replace(".", "")
    try:
        return float(raw), currency
    except ValueError:
        return None, currency


def _category(url: str) -> str:
    """Ürünün bulunduğu liste sayfasının yol adı (ana sayfa için boş)."""
    return urlparse(url).path.strip("/").split("/")[0]


async def _fetch_all(urls: list[str], folder: Path, limit: int) -> dict[str, str]:
    if not urls:
        return {}
    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(6)

    async def one(url: str) -> tuple[str, str | None]:
        async with semaphore:
            return url, await asyncio.to_thread(_fetch, url, folder, limit)

    results = await asyncio.gather(*(one(url) for url in urls))
    return {url: path for url, path in results if path}


def _fetch(url: str, folder: Path, limit: int) -> str | None:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(limit + 1)
            kind = response.headers.get_content_type()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if len(data) > limit or not data:
        return None
    name = Path(urlparse(url).path).name or "dosya"
    stem = re.sub(r"[^A-Za-z0-9._-]", "-", Path(name).stem)[:60] or "dosya"
    suffix = Path(name).suffix.lower() or _suffix_for(kind)
    digest = hashlib.sha1(url.encode()).hexdigest()[:8]
    target = folder / f"{stem}-{digest}{suffix}"
    target.write_bytes(data)
    return target.name


def _suffix_for(kind: str) -> str:
    return {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/svg+xml": ".svg",
        "image/avif": ".avif", "image/gif": ".gif", "font/woff2": ".woff2", "font/woff": ".woff",
        "video/mp4": ".mp4", "video/webm": ".webm",
    }.get(kind, "")  # fmt: skip


def save_report(report: DesignReport, folder: Path, folder_label: str) -> Path:
    """Ölçümleri, ürün listesini ve ekran görüntülerini klasöre yaz."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "urunler.json").write_text(
        json.dumps(collect_products(report, folder_label), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    logo = str(report.pages[0].get("logo", "")) if report.pages else ""
    if logo.lstrip().startswith("<svg"):
        (folder / INLINE_LOGO_FILE).write_text(logo, encoding="utf-8")
    pages = []
    for index, page in enumerate(report.pages, start=1):
        shot = page.pop("_screenshot_bytes", None)
        if isinstance(shot, bytes | bytearray):
            (folder / f"ekran-{index}.jpg").write_bytes(shot)
            page["screenshot"] = f"ekran-{index}.jpg"
        pages.append(page)
    document = {
        "kaynak": report.source,
        "yerel_gorseller": {url: f"images/{name}" for url, name in report.images.items()},
        "yerel_fontlar": {url: f"fonts/{name}" for url, name in report.fonts.items()},
        "yerel_videolar": {url: f"video/{name}" for url, name in report.videos.items()},
        "sayfalar": pages,
    }
    target = folder / "tasarim.json"
    target.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
    return target


def summarize(report: DesignReport, folder_label: str) -> str:
    """Modelin doğrudan uygulayacağı kısa tasarım özeti."""
    if not report.pages:
        return "Hiçbir sayfa ölçülemedi."
    home = report.pages[0]
    adresler = ", ".join(str(p.get("url")) for p in report.pages)
    lines = [
        f"Kaynak: {report.source}. {len(report.pages)} sayfa ölçüldü: {adresler}",
        f"Ayrıntılı ölçüler: {folder_label}/tasarim.json (bileşen HTML örnekleri), "
        f"ekran görüntüleri {folder_label}/ekran-N.jpg.",
        _logo_line(home, report, folder_label),
        _fonts_line(home, report, folder_label),
        "RENKLER (metin): " + _values(home.get("colors", {}).get("text", []), 6),
        "RENKLER (zemin): " + _values(home.get("colors", {}).get("background", []), 6),
        "TİPOGRAFİ: " + _scale_line(home.get("scale", {})),
        f"DÜZEN: içerik genişliği {_values(home.get('layout', {}).get('container', []), 3)}, "
        f"üst bilgi {_header(home)}",
        "MENÜ: "
        + ", ".join(link["text"] for link in home.get("navigation", {}).get("menu", [])[:14]),
    ]
    lines.extend(_component_line(page) for page in report.pages if page.get("components"))
    lines.extend(_section_lines(home, report, folder_label, "ana sayfa"))
    detail = next((page for page in report.pages if page.get("product")), None)
    if detail is not None:
        lines.append(_product_page_line(detail))
    products = collect_products(report, folder_label)
    if products:
        ornek = "; ".join(f"{item['ad']} — {item['fiyat']}" for item in products[:3])
        birim = next((item["para_birimi"] for item in products if item.get("para_birimi")), "")
        lines.append(
            f"ÜRÜNLER: {len(products)} ürün → {folder_label}/urunler.json (ad, fiyat, fiyat_sayi "
            f"[ondalık sayı, bunu kullan], para_birimi, yerel görsel, kategori, kaynak). Mağazaya "
            f"BUNLARI ürün olarak ekle. Örnek: {ornek}"
            + (f". Mağazanın para birimini {birim} yap." if birim else "")
        )
    filled = [
        b
        for b in home.get("buttons", [])
        if b["background"] not in ("rgba(0, 0, 0, 0)", "transparent") and len(b.get("text", "")) > 3
    ]
    if filled:
        b = filled[0]
        lines.append(
            f"BUTON: zemin {b['background']}, yazı {b['color']}, köşe {b['radius']}, "
            f"dolgu {b['padding']}, örnek '{b.get('text', '')}'"
        )
    if home.get("prices"):
        fiyat = home["prices"][0]
        stil = fiyat["style"]
        lines.append(f"FİYAT: '{fiyat['text']}' {stil['size']}/{stil['weight']} {stil['color']}")
    lines.append(
        f"GÖRSELLER: {len(report.images)} dosya indirildi → {folder_label}/images/ "
        "(eşleme: tasarim.json 'yerel_gorseller'). Logo ve ürün fotoğrafları başka markaya "
        "aittir: yerel çalışmada kullan, yayına almadan önce kendi görsellerinle değiştir."
    )
    lines.append(
        "Bu ölçüleri BİREBİR uygula (font, renk, boyut, köşe, boşluk); sayfayı BÖLÜMLER "
        "sırasıyla kur, bileşenleri tasarim.json'daki HTML örneklerine bakarak yaz. Dosyaları "
        f"{folder_label}/ içinden projenin kendi klasörüne (ör. temanın assets/ klasörü) "
        "KOPYALA ve oradan bağla. Sonucu ekran görüntüleriyle karşılaştır."
    )
    return "\n".join(lines)


def _values(items: list[dict[str, Any]], limit: int) -> str:
    return ", ".join(str(item["value"]) for item in items[:limit]) or "-"


#: Üst bilgideki logo satır içi SVG ise bu adla kaydedilir.
INLINE_LOGO_FILE = "logo.svg"


def _logo_line(home: dict[str, Any], report: DesignReport, folder_label: str) -> str:
    """Logonun yerel dosyası. Ölçüldü (8. kabul koşusu): özet logoyu söylemiyordu; model
    indirilen logo yerine yazıyla "SNEAKS UP" çizen bir SVG uydurdu."""
    logo = str(home.get("logo", ""))
    if logo in report.images:
        return f"LOGO: {folder_label}/images/{report.images[logo]} (üst bilgide BU dosyayı kullan)"
    if logo.lstrip().startswith("<svg"):
        return f"LOGO: {folder_label}/{INLINE_LOGO_FILE} (üst bilgide BU dosyayı kullan)"
    return "LOGO: ölçülemedi (üst bilgide site adını yazı tipiyle yaz)"


def _fonts_line(home: dict[str, Any], report: DesignReport, folder_label: str) -> str:
    fonts = home.get("fonts", {})
    line = "YAZI TİPLERİ: " + _values(fonts.get("used", []), 6)
    if report.fonts:
        line += f" | {len(report.fonts)} yazı tipi dosyası indirildi → {folder_label}/fonts/"
    if fonts.get("links"):
        line += " | bağlantı: " + ", ".join(fonts["links"][:2])
    return line


def _scale_line(scale: dict[str, Any]) -> str:
    return "; ".join(
        f"{tag} {style['size']}/{style['weight']} {style['family'].split(',')[0]}"
        for tag, style in scale.items()
        if style and tag in ("h1", "h2", "h3", "p", "a", "button", "body")
    )


def _component_line(page: dict[str, Any]) -> str:
    parts = []
    for comp in page.get("components", [])[:5]:
        style = comp["style"]
        title = comp.get("title") or {}
        parts.append(
            f"{comp['count']}× {comp['selector'].split(' > ')[-1][:48]} "
            f"({style['width']}×{style['height']}, köşe {style['radius']}, "
            f"başlık {title.get('size', '-')})"
        )
    return f"BİLEŞENLER ({page.get('url')}): " + "; ".join(parts)


_SECTION_NAMES = {
    "ust-bilgi": "ÜST BİLGİ", "kahraman": "KAHRAMAN (tam genişlik açılış)",
    "urun-listesi": "ÜRÜN ŞERİDİ/IZGARASI", "gorsel-izgara": "GÖRSEL IZGARASI",
    "afis": "AFİŞ", "alt-bilgi": "ALT BİLGİ", "metin": "METİN",
}  # fmt: skip


def _section_lines(
    page: dict[str, Any], report: DesignReport, folder_label: str, name: str
) -> list[str]:
    """Sayfanın yukarıdan aşağı bölümleri: tür, yükseklik, başlık, yerel medya."""
    sections = page.get("sections", [])
    if not sections:
        return []

    def local(url: str) -> str:
        if url in report.videos:
            return f"{folder_label}/video/{report.videos[url]}"
        if url in report.images:
            return f"{folder_label}/images/{report.images[url]}"
        return ""

    lines = [f"BÖLÜMLER ({name}, yukarıdan aşağı — bu sırayla kur):"]
    for index, section in enumerate(sections, start=1):
        parts = [f"{_SECTION_NAMES.get(section['kind'], section['kind'])} {section['height']}px"]
        video = section.get("video") or {}
        media = [
            path
            for url in (
                video.get("src", ""),
                video.get("poster", ""),
                section.get("backgroundImage", ""),
                *section.get("images", [])[:2],
            )
            if url and (path := local(url))
        ]
        if video:
            parts.append("VİDEO" + ("" if video.get("src") in report.videos else " (indirilemedi)"))
        if media:
            parts.append("medya " + ", ".join(dict.fromkeys(media)))
        if section.get("headings"):
            heading = section["headings"][0]
            font = heading["font"]
            parts.append(
                f"başlık '{heading['text']}' ({font['family'].split(',')[0]} "
                f"{font['size']}/{font['weight']} {font['color']})"
            )
        if section.get("buttons"):
            parts.append("düğme " + ", ".join(f"'{text}'" for text in section["buttons"][:3]))
        if section.get("items"):
            parts.append(f"{section['items']} fiyatlı öğe")
        if section["background"] not in ("rgba(0, 0, 0, 0)", "transparent"):
            parts.append(f"zemin {section['background']}")
        lines.append(f"  {index}. " + " | ".join(parts))
    return lines


def _product_page_line(page: dict[str, Any]) -> str:
    product = page["product"]
    button = product.get("buyButton", {})
    options = ", ".join(dict.fromkeys(product.get("options", []))) or "-"
    return (
        f"ÜRÜN SAYFASI ({page.get('url')}): '{product.get('name')}' {product.get('price')}, "
        f"{len(product.get('images', []))} galeri görseli, seçenekler {options}; "
        f"düğme '{button.get('text', '')}' "
        f"zemin {button.get('background', '-')}, yazı {button.get('color', '-')}, "
        f"{button.get('width', '-')}×{button.get('height', '-')}, köşe {button.get('radius', '-')}"
    )


def _header(page: dict[str, Any]) -> str:
    header = page.get("layout", {}).get("header")
    if not header:
        return "-"
    sticky = ", yapışkan" if header.get("sticky") else ""
    return f"{header['height']}px yükseklik, zemin {header['background']}{sticky}"


def same_site(url: str, other: str) -> bool:
    return urlparse(url).netloc == urlparse(urljoin(url, other)).netloc


def reference_pages(root: Path) -> list[dict[str, Any]]:
    """Projede kayıtlı kaynak ölçüm sayfaları (yoksa ya da okunamıyorsa boş liste)."""
    try:
        document = json.loads((root / DEFAULT_FOLDER / "tasarim.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    pages = document.get("sayfalar") if isinstance(document, dict) else None
    return [page for page in pages if isinstance(page, dict)] if isinstance(pages, list) else []

"""Site kopyası denetçisinin tarayıcı yarısı: sayfaları açar, alışveriş akışını dener.

Ölçülenler sayısaldır (görsel yargı yok): HTTP durumu, PHP hata metni, ızgara
sütunu (kartların ilk satırdaki farklı x konumları), sepete ekle düğmesinin
`form.cart` içinde olup olmadığı, sepete ekleme sonrası sepetin içeriği, ödeme
formu ve kapıda ödemeyle sipariş denemesi, kaynak siteye giden istekler
(hotlink) ve ana sayfanın kaynakla gri ton benzerliği.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from evals.kabul.model import Check

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

VIEWPORT_WIDTH = 1440
VIEWPORT_HEIGHT = 900
#: Benzerlikte karşılaştırılan üst bölüm yüksekliği (piksel): ilk iki ekran.
COMPARE_HEIGHT = 1800
#: Karşılaştırma öncesi küçültme boyutu; ince ayrıntı değil yerleşim ölçülür.
COMPARE_SIZE = (144, 180)
NAVIGATION_TIMEOUT_MS = 45_000
ACTION_TIMEOUT_MS = 15_000
PHP_ERROR_MARKERS = ("Fatal error", "Parse error", "Uncaught Error", "Warning</b>:")
#: Varsayılan WordPress kenar çubuğunun işaretleri (temada kalmış "Sayfalar" listesi).
DEFAULT_SIDEBAR_SELECTOR = "#secondary .widget, .widget_pages, .widget_recent_entries"
PRODUCT_CARD_SELECTOR = "ul.products li.product, .wc-block-grid__product, li.product"


class ProbeUnavailableError(Exception):
    """Playwright ya da tarayıcı yok: ölçüm yapılamadı (koşu geçersiz)."""


@dataclass(frozen=True, slots=True)
class WooPages:
    """WP-CLI'dan okunan WooCommerce sayfa adresleri."""

    shop: str
    cart: str
    checkout: str
    product: str


@dataclass(frozen=True, slots=True)
class StoreProbe:
    """Tarayıcı ölçümünün sonucu."""

    checks: tuple[Check, ...]
    grid_columns: int
    similarity: float
    checkout_note: str


def _has_php_error(html: str) -> bool:
    return any(isaret in html for isaret in PHP_ERROR_MARKERS)


def grid_columns(lefts: list[float], tops: list[float]) -> int:
    """İlk satırdaki kart sayısı: en üstteki kartla aynı satırdaki farklı x konumları."""
    if not tops:
        return 0
    ilk = min(tops)
    return len({round(sol) for sol, ust in zip(lefts, tops, strict=True) if abs(ust - ilk) < 8})


def similarity(first_png: bytes, second_png: bytes) -> float:
    """İki ekran görüntüsünün küçültülmüş gri ton benzerliği (1 = aynı)."""
    from PIL import Image, ImageChops, ImageStat  # tembel: yalnız denetimde gerekli

    resimler = []
    for veri in (first_png, second_png):
        resim = Image.open(io.BytesIO(veri)).convert("L")
        resim = resim.crop((0, 0, resim.width, min(resim.height, COMPARE_HEIGHT)))
        resimler.append(resim.resize(COMPARE_SIZE))
    fark = ImageStat.Stat(ImageChops.difference(resimler[0], resimler[1])).mean[0]
    return round(1.0 - fark / 255.0, 3)


def probe_store(base_url: str, pages: WooPages, source_url: str) -> StoreProbe:
    """Mağazayı tarayıcıda ölç; Playwright yoksa `ProbeUnavailableError`."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as hata:
        raise ProbeUnavailableError("playwright kurulu değil") from hata
    # Alt alan adları (cdn.site.com) da kaynağa hotlink'tir; www. öneki atılır.
    kaynak_alan = (urlparse(source_url).hostname or "").removeprefix("www.")
    try:
        with sync_playwright() as oynatici:
            tarayici = oynatici.chromium.launch()
            try:
                return _run(tarayici, base_url, pages, source_url, kaynak_alan)
            finally:
                tarayici.close()
    except PlaywrightError as hata:
        if "Executable doesn't exist" in str(hata):
            raise ProbeUnavailableError("Chromium kurulu değil") from hata
        raise


def _run(
    tarayici: Browser, base_url: str, pages: WooPages, source_url: str, host: str
) -> StoreProbe:
    baglam = tarayici.new_context(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
    baglam.set_default_timeout(ACTION_TIMEOUT_MS)
    hotlink: list[str] = []
    if host:
        baglam.on("request", lambda istek: _note_hotlink(hotlink, istek.url, host))
    sayfa = baglam.new_page()
    ana = sayfa.goto(base_url + "/", timeout=NAVIGATION_TIMEOUT_MS, wait_until="load")
    ana_html = sayfa.content()
    ana_png = sayfa.screenshot(full_page=True)
    kenar = sayfa.locator(DEFAULT_SIDEBAR_SELECTOR).count()
    kirik_ana = _broken_images(sayfa)
    checks = [
        Check(
            "ana_sayfa_acildi",
            ana is not None and ana.ok and not _has_php_error(ana_html),
            f"HTTP {ana.status if ana else 'yok'}",
        ),
        Check("varsayilan_kenar_cubugu_yok", kenar == 0, f"{kenar} varsayılan widget"),
        _image_check("ana_sayfa_gorselleri", kirik_ana),
    ]
    sutun = _grid(sayfa, pages.shop)
    checks.append(_image_check("magaza_gorselleri", _broken_images(sayfa)))
    checks.append(_product_form(sayfa, pages.product))
    checks.append(_add_to_cart(sayfa, pages))
    odeme, not_ = _checkout(sayfa, pages.checkout)
    checks.append(odeme)
    checks.append(Check("kaynaga_hotlink_yok", not hotlink, f"{len(hotlink)} istek {host} alanına"))
    return StoreProbe(tuple(checks), sutun, _source_similarity(tarayici, source_url, ana_png), not_)


#: Kırık (yüklenmemiş) ya da WooCommerce yer tutucusu görsel oranı bu değeri
#: aşarsa madde düşer. Başlangıç eşiği; taban ölçümüyle sabitlenecek.
MAX_BROKEN_IMAGE_RATIO = 0.1
_BROKEN_IMAGES_JS = """() => {
  const imgs = [...document.images].filter(i => i.offsetParent !== null);
  const bad = imgs.filter(i => (i.complete && i.naturalWidth === 0)
    || /woocommerce-placeholder|placeholder\\.(png|jpg|webp)/.test(i.currentSrc || i.src));
  return [bad.length, imgs.length];
}"""


def _broken_images(sayfa: Page) -> tuple[int, int]:
    """Görünür görsellerden kırık ya da yer tutucu olanların sayısı ve toplam."""
    sayfa.wait_for_timeout(1500)
    kirik, toplam = sayfa.evaluate(_BROKEN_IMAGES_JS)
    return int(kirik), int(toplam)


def _image_check(name: str, counts: tuple[int, int]) -> Check:
    kirik, toplam = counts
    oran = kirik / toplam if toplam else 1.0
    return Check(
        name,
        toplam > 0 and oran <= MAX_BROKEN_IMAGE_RATIO,
        f"{kirik}/{toplam} görsel kırık ya da yer tutucu (en çok {MAX_BROKEN_IMAGE_RATIO:.0%})",
    )


def _note_hotlink(hotlink: list[str], url: str, host: str) -> None:
    if host in (urlparse(url).hostname or ""):
        hotlink.append(url)


def _grid(sayfa: Page, shop_url: str) -> int:
    if not shop_url:
        return 0
    sayfa.goto(shop_url, timeout=NAVIGATION_TIMEOUT_MS)
    kutular = sayfa.locator(PRODUCT_CARD_SELECTOR).evaluate_all(
        "els => els.filter(e => e.offsetParent).map(e => e.getBoundingClientRect())"
        ".map(r => [r.left, r.top])"
    )
    return grid_columns([k[0] for k in kutular], [k[1] for k in kutular])


def _product_form(sayfa: Page, product_url: str) -> Check:
    if not product_url:
        return Check("sepete_ekle_formda", False, "yayında ürün yok")
    sayfa.goto(product_url, timeout=NAVIGATION_TIMEOUT_MS)
    formda = sayfa.locator("form.cart button[type=submit], form.cart [name=add-to-cart]").count()
    disarida = sayfa.locator(".single_add_to_cart_button").count() - formda
    return Check(
        "sepete_ekle_formda",
        formda > 0,
        f"form.cart içinde {formda}, dışında {max(disarida, 0)} sepete ekle düğmesi",
    )


def _add_to_cart(sayfa: Page, pages: WooPages) -> Check:
    from playwright.sync_api import Error as PlaywrightError

    if not pages.product or not pages.cart:
        return Check("sepete_ekleme_calisir", False, "ürün ya da sepet sayfası yok")
    try:
        sayfa.goto(pages.product, timeout=NAVIGATION_TIMEOUT_MS)
        for secim in sayfa.locator("form.cart select").all():
            degerler = secim.locator("option").evaluate_all(
                "os => os.map(o => o.value).filter(v => v)"
            )
            if degerler:
                secim.select_option(degerler[0])
        sayfa.locator("form.cart button[type=submit]").first.click()
        sayfa.wait_for_load_state("load")
        sayfa.goto(pages.cart, timeout=NAVIGATION_TIMEOUT_MS)
        ogeler = sayfa.locator(".cart_item, .wc-block-cart-items__row").count()
    except PlaywrightError as hata:
        return Check("sepete_ekleme_calisir", False, f"akış kırıldı: {str(hata)[:160]}")
    return Check("sepete_ekleme_calisir", ogeler > 0, f"sepette {ogeler} satır")


def _checkout(sayfa: Page, checkout_url: str) -> tuple[Check, str]:
    """Ödeme formunu doldurup kapıda ödemeyle sipariş vermeyi dene."""
    from evals.kabul.areas.site_clone_checkout import place_order

    return place_order(sayfa, checkout_url, NAVIGATION_TIMEOUT_MS)


def _source_similarity(tarayici: Browser, source_url: str, clone_png: bytes) -> float:
    from playwright.sync_api import Error as PlaywrightError

    baglam = tarayici.new_context(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
    try:
        sayfa = baglam.new_page()
        sayfa.goto(source_url, timeout=NAVIGATION_TIMEOUT_MS, wait_until="load")
        return similarity(sayfa.screenshot(full_page=True), clone_png)
    except PlaywrightError:
        return 0.0
    finally:
        baglam.close()

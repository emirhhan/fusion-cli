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

from evals.kabul.areas.site_clone_menu import MenuPanel, menu_check, menu_panels_opened
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
    kopya_tasma = int(sayfa.evaluate(_OVERFLOW_JS))
    kopya_menu = menu_panels_opened(sayfa)
    checks.append(_slider_check(sayfa))
    sutun = _grid(sayfa, pages.shop)
    checks.append(_image_check("magaza_gorselleri", _broken_images(sayfa)))
    checks.append(_store_style_check(sayfa, pages.shop))
    checks.append(_product_form(sayfa, pages.product))
    checks.append(_add_to_cart(sayfa, pages))
    odeme, not_ = _checkout(sayfa, pages.checkout)
    checks.append(odeme)
    checks.append(Check("kaynaga_hotlink_yok", not hotlink, f"{len(hotlink)} istek {host} alanına"))
    benzerlik, kaynak_tasma, kaynak_menu = _source_similarity(tarayici, source_url, ana_png)
    checks.insert(3, overflow_check(kopya_tasma, kaynak_tasma))
    checks.insert(4, menu_check(kopya_menu, kaynak_menu))
    return StoreProbe(tuple(checks), sutun, benzerlik, not_)


#: Betikle ölçülenen kaydırıcıların slayt sınıfları (swiper, slick, splide, embla…).
SLIDE_SELECTOR = (
    ".swiper-slide, .slick-slide, .splide__slide, .embla__slide, .glide__slide, "
    ".keen-slider__slide, .carousel-item"
)
#: Slayttaki görsel slaytın bu oranından darsa "büzülmüş" sayılır. Ölçüldü (4 Ekim):
#: 250 px'lik slaytta görsel 62 px'e düşmüştü (0,25); sağlam kopyada oran 1,0.
MIN_SLIDE_IMAGE_RATIO = 0.5
#: WooCommerce ve tarayıcı varsayılan renkleri: mağaza sayfası bunları taşıyorsa
#: kaynağın görünümü oraya hiç uygulanmamıştır.
DEFAULT_LINK_COLOR = "rgb(0, 0, 238)"
DEFAULT_WOO_COLORS = frozenset(
    {"rgb(127, 84, 179)", "rgb(149, 142, 9)", "rgb(119, 164, 100)", "rgb(235, 233, 235)"}
)
_SLIDER_JS = """(selector) => [...document.querySelectorAll(selector)].flatMap((slide) => {
  const width = slide.getBoundingClientRect().width;
  const image = slide.querySelector('img');
  if (!image || width < 40) return [];
  return [image.getBoundingClientRect().width / width];
})"""
_STORE_STYLE_JS = """() => {
  const style = (selector, property) => {
    const node = document.querySelector(selector);
    return node ? getComputedStyle(node)[property] : '';
  };
  return {
    baslik: style('ul.products li.product a', 'color'),
    fiyat: style('ul.products li.product .price', 'color'),
    dugme: style('ul.products li.product .button', 'backgroundColor'),
  };
}"""


def default_style_markers(colors: dict[str, str]) -> list[str]:
    """Mağaza sayfasında varsayılan (kaynağa uyarlanmamış) kalan öğelerin adları."""
    kalan = []
    if colors.get("baslik") == DEFAULT_LINK_COLOR:
        kalan.append("ürün adı varsayılan bağlantı mavisi")
    if colors.get("fiyat") in DEFAULT_WOO_COLORS:
        kalan.append("fiyat WooCommerce varsayılan rengi")
    if colors.get("dugme") in DEFAULT_WOO_COLORS:
        kalan.append("düğme WooCommerce varsayılan rengi")
    return kalan


def shrunken_slides(ratios: list[float]) -> int:
    """Görseli slaytına göre büzülmüş slayt sayısı."""
    return sum(1 for oran in ratios if oran < MIN_SLIDE_IMAGE_RATIO)


_OVERFLOW_JS = "() => document.documentElement.scrollWidth - window.innerWidth"
#: Alt-piksel yuvarlama payı (px).
OVERFLOW_TOLERANCE_PX = 2


def overflow_check(clone_px: int, source_px: int | None) -> Check:
    """Kopya kaynaktan fazla taşıyorsa kusur. Ölçüldü (dalga45/46): sneaksup.com 1440 px'te
    kendisi 365 px taşıyor; mutlak ölçüm birebir kopyayı kusurlu sayıyordu."""
    izin = max(source_px or 0, 0) + OVERFLOW_TOLERANCE_PX
    kaynak = "ölçülmedi" if source_px is None else f"{max(source_px, 0)} px"
    return Check(
        "ana_sayfa_yatay_tasmiyor",
        clone_px <= izin,
        f"taşma: {max(clone_px, 0)} px (kaynak {kaynak})",
    )


def _slider_check(sayfa: Page) -> Check:
    oranlar = [float(oran) for oran in sayfa.evaluate(_SLIDER_JS, SLIDE_SELECTOR)]
    buzulen = shrunken_slides(oranlar)
    return Check(
        "kaydirici_gorselleri_dolu",
        buzulen == 0,
        f"{buzulen}/{len(oranlar)} slaytta görsel büzülmüş" if oranlar else "kaydırıcı yok",
    )


def _store_style_check(sayfa: Page, shop_url: str) -> Check:
    if not shop_url:
        return Check("magaza_kaynak_gorunumunde", False, "mağaza sayfası yok")
    kalan = default_style_markers(dict(sayfa.evaluate(_STORE_STYLE_JS)))
    return Check("magaza_kaynak_gorunumunde", not kalan, "; ".join(kalan))


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


def _source_similarity(
    tarayici: Browser, source_url: str, clone_png: bytes
) -> tuple[float, int, tuple[MenuPanel, ...]]:
    """Kaynak benzerliği, yatay taşması ve açılan menülerin içerik kanıtı."""
    from playwright.sync_api import Error as PlaywrightError

    # Kaynak açılamazsa bu bir ÖLÇÜM hatasıdır, kopyanın kusuru değil: bir kez daha
    # denenir, yine olmazsa ProbeUnavailableError koşuyu geçersiz kılar (ölçüldü,
    # 4 Ekim: kaynak alınamadığı için benzerlik 0,00 yazılıp kopya "kaldı" sayıldı).
    son_hata: Exception | None = None
    for _ in range(2):
        baglam = tarayici.new_context(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
        try:
            sayfa = baglam.new_page()
            sayfa.goto(source_url, timeout=NAVIGATION_TIMEOUT_MS, wait_until="load")
            kaynak_png = sayfa.screenshot(full_page=True)
            tasma = int(sayfa.evaluate(_OVERFLOW_JS))
            return similarity(kaynak_png, clone_png), tasma, menu_panels_opened(sayfa)
        except PlaywrightError as hata:
            son_hata = hata
        finally:
            baglam.close()
    raise ProbeUnavailableError(f"kaynak site ölçülemedi: {str(son_hata)[:160]}")

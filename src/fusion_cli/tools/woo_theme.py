"""Yakalanmış siteden WooCommerce uyumlu klasik tema iskeleti üret.

Ölçüldü (17 kabul koşusu, üç ayrı ajan): model temayı her seferinde sıfırdan
yazdı, WooCommerce'in sepete ekle formunu ve stillerini söktü (ölü düğme, tek
sütun mağaza) ve 20 KB'lık dosyaları tek çağrıda yazmaya çalışırken zaman aşımına
uğradı. Burada görünüm DETERMİNİSTİK kurulur:

- `header.php` / `footer.php` yakalanan başlık ve altlıktan, `front-page.php` ana
  sayfanın gövdesinden üretilir; CSS tek `kopya.css` dosyasıdır.
- `woocommerce.php` mağaza, ürün, sepet ve ödeme sayfalarını GERÇEK WooCommerce
  şablonlarıyla (`woocommerce_content()`) aynı başlık/altlık arasında açar;
  WooCommerce stilleri SÖKÜLMEZ, kopya CSS onlardan sonra yüklenir.

Modele kalan iş dinamik bağlamadır (menü bağlantıları, sepet sayacı, mağaza ve
ürün sayfasının stilini referans görüntüye yaklaştırmak).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from .site_capture import SiteCapture, drop_remote_srcset, localize, same_site_paths
from .site_clicks import INTERACTIONS_RUNTIME
from .theme_responsive import build_responsive_theme
from .woo_store_css import store_css

#: PHP şablonlarında tema klasörü adresi.
THEME_URI = "<?php echo esc_url( get_template_directory_uri() ); ?>/"
#: Yakalanan HTML'de PHP açılış etiketi PHP kodu gibi yorumlanmasın.
_PHP_OPEN = re.compile(r"<\?")
_SLUG = re.compile(r"[^a-z0-9-]+")


@dataclass(frozen=True, slots=True)
class ThemeFiles:
    """Yazılan tema: klasör ve dosya listesi."""

    folder: Path
    files: tuple[str, ...]
    responsive_paths: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()


def theme_slug(source_url: str) -> str:
    """Kaynak alan adından tema klasörü adı (ör. sneaksup-kopya)."""
    host = (urlparse(source_url).hostname or "site").removeprefix("www.").split(".")[0]
    return f"{_SLUG.sub('-', host.lower()).strip('-') or 'site'}-kopya"


def _safe(html: str) -> str:
    return _PHP_OPEN.sub("&lt;?", html)


def _style_header(name: str, source_url: str) -> str:
    return (
        "/*\n"
        f"Theme Name: {name}\n"
        f"Description: {source_url} adresinden yakalanan görünümle üretilen kopya tema. "
        "Yalnız yerel test içindir; marka, görsel ve metinler üçüncü tarafa aittir.\n"
        "Version: 1.0\n"
        "*/\n"
    )


_FUNCTIONS = """<?php
/**
 * Kopya tema: WooCommerce desteği ve stil sırası.
 * WooCommerce stilleri SÖKÜLMEZ; kopya CSS onlardan sonra yüklenir ki form,
 * sepet ve ödeme bileşenleri çalışır kalsın.
 */
add_action( 'after_setup_theme', function () {
	add_theme_support( 'woocommerce' );
	add_theme_support( 'title-tag' );
	add_theme_support( 'post-thumbnails' );
	register_nav_menus( array( 'primary' => 'Ana menü' ) );
} );
add_action( 'wp_enqueue_scripts', function () {
	wp_enqueue_style( 'kopya', get_template_directory_uri() . '/kopya.css', array(), '1.0' );
	wp_enqueue_style( 'kopya-ek', get_stylesheet_uri(), array( 'kopya' ), '1.0' );
	// Kaynak betik kopyada yok: sekme halleri ve kaydırıcı okları yerel betikle çalışır.
	wp_enqueue_script(
		'kopya-etkilesim', get_template_directory_uri() . '/etkilesim.js', array(), '1.0', true
	);
}, 20 );
"""

_HEADER_TEMPLATE = """<!doctype html>
<html <?php language_attributes(); ?>>
<head>
<meta charset="<?php bloginfo( 'charset' ); ?>">
<meta name="viewport" content="width=device-width, initial-scale=1">
<?php wp_head(); ?>
</head>
<body <?php body_class( '{body_class}' ); ?>>
<?php wp_body_open(); ?>
{header}
"""

_FOOTER_TEMPLATE = """{footer}
<?php wp_footer(); ?>
</body>
</html>
"""

_WOOCOMMERCE = """<?php get_header(); ?>
<main class="kopya-woocommerce">
<?php woocommerce_content(); ?>
</main>
<?php get_footer(); ?>
"""

_PAGE = """<?php get_header(); ?>
<main class="kopya-sayfa">
<?php while ( have_posts() ) : the_post(); ?>
<h1><?php the_title(); ?></h1>
<?php the_content(); ?>
<?php endwhile; ?>
</main>
<?php get_footer(); ?>
"""


#: Mağaza sayfalarının kaynak sitelerde sık görülen yolları → WooCommerce sayfası.
_STORE_PATHS = {
    "wc_get_cart_url()": ("sepet", "sepetim", "cart", "basket", "bag"),
    "wc_get_page_permalink( 'myaccount' )": (
        "hesabim", "hesap", "uyelik", "giris", "account", "my-account", "login", "uye-girisi",
    ),
    "wc_get_page_permalink( 'shop' )": ("magaza", "urunler", "shop", "products", "tum-urunler"),
}  # fmt: skip


#: Betikle çalışan simge düğmeleri (aria-label) → bağlantı hedefi. Kopya statik olduğu
#: için düğmeler ölü kalıyordu (ölçüldü: sneaksup'ta sepet/hesap/arama düğmeydi).
_BUTTON_TARGETS = (
    (re.compile(r"sepet|cart|basket|bag", re.IGNORECASE), "wc_get_cart_url()"),
    (
        re.compile(r"hesa[bp]|account|giriş|giris|login|profil|üye|uye", re.IGNORECASE),
        "wc_get_page_permalink( 'myaccount' )",
    ),
    (re.compile(r"\bara\b|search|arama", re.IGNORECASE), "home_url( '/?s=&post_type=product' )"),
)
_LABELED_BUTTON = re.compile(r'<button(?P<attrs>[^>]*aria-label="(?P<label>[^"]*)"[^>]*)>')


def buttons_to_links(html: str) -> str:
    """Sepet/hesap/arama simge düğmelerini WooCommerce bağlantısına çevir."""
    parcalar: list[str] = []
    konum = 0
    for eslesme in _LABELED_BUTTON.finditer(html):
        ifade = next(
            (hedef for desen, hedef in _BUTTON_TARGETS if desen.search(eslesme.group("label"))),
            None,
        )
        kapanis = html.find("</button>", eslesme.end())
        if ifade is None or kapanis < 0 or eslesme.start() < konum:
            continue
        nitelikler = re.sub(r'\s(type|tabindex)="[^"]*"', "", eslesme.group("attrs"))
        parcalar.append(html[konum : eslesme.start()])
        parcalar.append(f'<a href="<?php echo esc_url( {ifade} ); ?>"{nitelikler}>')
        parcalar.append(html[eslesme.end() : kapanis] + "</a>")
        konum = kapanis + len("</button>")
    parcalar.append(html[konum:])
    return "".join(parcalar)


def wire_store_links(html: str, category_slugs: tuple[str, ...]) -> str:
    """Kaynak sitenin kategori/sepet/hesap bağlantılarını WooCommerce adreslerine bağla.

    Ölçüldü (4 Ekim, clone_site sonrası koşu): model menüyü bağlamak için tek satırlık
    başlık dosyasında 170+ kabuk komutuyla metin değiştirmeye çalıştı. Eşleşme
    deterministik yapılır: yolun ilk parçası bir ürün kategorisiyse kategori sayfası,
    bilinen sepet/hesap/mağaza yollarıysa ilgili WooCommerce sayfası.
    """
    hedefler: dict[str, str] = {}
    for slug in category_slugs:
        hedefler[slug] = f"home_url( '/?product_cat={slug}' )"
    for ifade, yollar in _STORE_PATHS.items():
        for yol in yollar:
            hedefler.setdefault(yol, ifade)

    def _bagla(match: re.Match[str]) -> str:
        yol = match.group(1)
        ilk = yol.split("/", 1)[0].lower()
        ifade = hedefler.get(ilk) if "/" not in yol.rstrip("/") else None
        if ifade is None:
            # Karşılığı olmayan sayfa (marka, kampanya) 404 vermesin: mağaza araması.
            kelimeler = quote_plus(yol.rstrip("/").rsplit("/", 1)[-1].replace("-", " "))
            ifade = f"home_url( '/?s={kelimeler}&post_type=product' )"
        return f'href="<?php echo esc_url( {ifade} ); ?>"'

    bagli = re.sub(r'href="/([A-Za-z0-9_\-/]+)(?:\?[^"]*)?"', _bagla, buttons_to_links(html))
    # Sepet bağlantısına canlı sayaç: kopya statik HTML'dir, sepet içeriğini bilmez.
    return re.sub(
        r'(<a[^>]*href="<\?php echo esc_url\( wc_get_cart_url\(\) \); \?>"[^>]*>)',
        lambda m: m.group(1) + CART_COUNTER,
        bagli,
    )


#: Sepet bağlantısına eklenen sayaç (WooCommerce oturumu yoksa 0).
CART_COUNTER = (
    '<span class="kopya-sepet-sayaci"><?php echo WC()->cart ? '
    "(int) WC()->cart->get_cart_contents_count() : 0; ?></span>"
)
_CART_COUNTER_CSS = (
    "\n.kopya-sepet-sayaci { position: absolute; top: -6px; right: -8px; min-width: 16px; "
    "height: 16px; border-radius: 8px; background: #111; color: #fff; font-size: 10px; "
    "line-height: 16px; text-align: center; }\n"
    "a:has(> .kopya-sepet-sayaci) { position: relative; }\n"
)


def _prepare(html: str, capture: SiteCapture, source_url: str) -> str:
    # Sıra önemli: önce kaynaktaki `<?` kaçırılır, SONRA tema adresi (PHP) yerleştirilir.
    # Tersi kendi PHP etiketimizi de kaçırıyordu (ölçüldü: 727 görsel adresi bozuldu).
    yerel = drop_remote_srcset(localize(_safe(html), capture.assets, THEME_URI))
    return same_site_paths(yerel, source_url)


def _inner_page_css(header_offset: int) -> str:
    """Sabit başlık iç sayfalarda içeriğin üstüne binmesin."""
    if header_offset <= 0:
        return ""
    return f"\n.kopya-woocommerce, .kopya-sayfa {{ padding-top: {header_offset}px; }}\n"


def _apply_responsive(
    dosyalar: dict[str, str],
    capture: SiteCapture,
    source_url: str,
    category_slugs: tuple[str, ...],
) -> bool:
    """Ana sayfanın doğrulanmış parçalarını etkin varyant runtime'ına bağla."""
    ana = capture.pages[0]

    def prepare(text: str) -> str:
        return wire_store_links(_prepare(text, capture, source_url), category_slugs)

    responsive = build_responsive_theme(ana, capture, prepare, THEME_URI)
    if responsive is None:
        return False
    if responsive is not None:
        dosyalar["header.php"] = _HEADER_TEMPLATE.format(
            body_class=_safe(ana.body_class).replace("'", ""), header=responsive.header
        )
        dosyalar["front-page.php"] = (
            "<?php get_header(); ?>\n" + responsive.main + "\n<?php get_footer(); ?>\n"
        )
        dosyalar["footer.php"] = _FOOTER_TEMPLATE.format(footer=responsive.footer)
        dosyalar["responsive.js"] = responsive.runtime
        dosyalar["functions.php"] += (
            "\nadd_action( 'wp_enqueue_scripts', function () {\n"
            "\twp_enqueue_script( 'kopya-responsive', "
            "get_template_directory_uri() . '/responsive.js', "
            "array(), '1.0', true );\n}, 20 );\n"
        )
        dosyalar["style.css"] += (
            "\n.kopya-woocommerce, .kopya-sayfa { padding-top: "
            "var(--fusion-header-offset, 0px); }\nbody:not(.home)::before { height: "
            "var(--fusion-header-offset, 0px); }\n"
        )
    return True


def _responsive_problems(capture: SiteCapture, paths: tuple[str, ...]) -> tuple[str, ...]:
    """Kaynak DOM seçimi geometri veya kaynak JavaScript başarısı sayılmaz."""
    if paths:
        return (
            "Responsive aktarım yerel JavaScript gerektirir; menü üzerine gelme panelleri, "
            "sekme halleri ve kaydırıcı okları yerel olarak aktarıldı, diğer kaynak "
            "etkileşimleri aktarılmadı. Ana sayfa dışında yakalanmış DOM varyantları tema "
            "rotasına aktarılmadı.",
            "Kaynak signature geçişi piksel geometrisi kanıtı değildir; yakalanmayan viewportlarda "
            "yerleşim ve etkileşim ayrıca doğrulanmalıdır.",
        )
    if len(capture.pages[0].transitions) > 1:
        return (
            "Kaynak genişlik geçişleri bağlı viewport zincirini açıklamıyor; "
            "çoklu tema aktarımı uygulanmadı.",
        )
    return ()


def write_theme(
    capture: SiteCapture,
    themes_dir: Path,
    source_url: str,
    category_slugs: tuple[str, ...] = (),
    design_page: Mapping[str, Any] | None = None,
) -> ThemeFiles:
    """Tema dosyalarını yaz; varlıklar zaten `<tema>/assets/` altında olmalı."""
    if not capture.pages:
        raise ValueError("yakalanmış sayfa yok")
    slug = theme_slug(source_url)
    folder = themes_dir / slug
    folder.mkdir(parents=True, exist_ok=True)
    ana = capture.pages[0]
    dosyalar = {
        "style.css": _style_header(slug, source_url)
        + "/* Elle düzeltmeler buraya; görünümün kendisi kopya.css'tedir. */\n"
        + store_css(design_page, ana.header_offset)
        + _inner_page_css(ana.header_offset)
        + _CART_COUNTER_CSS,
        "kopya.css": localize(capture.css, capture.assets, ""),
        "functions.php": _FUNCTIONS,
        "etkilesim.js": INTERACTIONS_RUNTIME.read_text(encoding="utf-8"),
        "header.php": _HEADER_TEMPLATE.format(
            body_class=_safe(ana.body_class).replace("'", ""),
            header=wire_store_links(_prepare(ana.header, capture, source_url), category_slugs),
        ),
        "footer.php": _FOOTER_TEMPLATE.format(
            footer=wire_store_links(_prepare(ana.footer, capture, source_url), category_slugs)
        ),
        "front-page.php": "<?php get_header(); ?>\n"
        + wire_store_links(_prepare(ana.main, capture, source_url), category_slugs)
        + "\n<?php get_footer(); ?>\n",
        "woocommerce.php": _WOOCOMMERCE,
        "page.php": _PAGE,
        "index.php": _PAGE,
    }

    has_responsive = _apply_responsive(dosyalar, capture, source_url, category_slugs)
    for ad, icerik in dosyalar.items():
        (folder / ad).write_text(icerik, encoding="utf-8")
    referans = folder / "referans"
    referans.mkdir(exist_ok=True)
    for sira, sayfa in enumerate(capture.pages):
        for genislik, goruntu in sayfa.screenshots.items():
            (referans / f"sayfa{sira}-{genislik}.jpg").write_bytes(goruntu)
        (referans / f"sayfa{sira}.html").write_text(
            _prepare(sayfa.header + sayfa.main + sayfa.footer, capture, source_url),
            encoding="utf-8",
        )
    paths = (ana.url,) if has_responsive else ()
    problems = _responsive_problems(capture, paths)
    return ThemeFiles(folder, tuple(sorted(dosyalar)), paths, problems)

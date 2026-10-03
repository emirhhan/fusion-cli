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
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .site_capture import SiteCapture, drop_remote_srcset, localize, same_site_paths

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


def _prepare(html: str, capture: SiteCapture, source_url: str) -> str:
    # Sıra önemli: önce kaynaktaki `<?` kaçırılır, SONRA tema adresi (PHP) yerleştirilir.
    # Tersi kendi PHP etiketimizi de kaçırıyordu (ölçüldü: 727 görsel adresi bozuldu).
    yerel = drop_remote_srcset(localize(_safe(html), capture.assets, THEME_URI))
    return same_site_paths(yerel, source_url)


def _inner_page_css(header_offset: int) -> str:
    """Sabit başlık iç sayfalarda içeriğin üstüne binmesin."""
    if header_offset <= 0:
        return ""
    return (
        f"\n.kopya-woocommerce, .kopya-sayfa {{ padding-top: {header_offset}px; }}\n"
        ".kopya-woocommerce { max-width: 1440px; margin: 0 auto; padding-left: 16px; "
        "padding-right: 16px; }\n"
    )


def write_theme(capture: SiteCapture, themes_dir: Path, source_url: str) -> ThemeFiles:
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
        + _inner_page_css(ana.header_offset),
        "kopya.css": localize(capture.css, capture.assets, ""),
        "functions.php": _FUNCTIONS,
        "header.php": _HEADER_TEMPLATE.format(
            body_class=_safe(ana.body_class).replace("'", ""),
            header=_prepare(ana.header, capture, source_url),
        ),
        "footer.php": _FOOTER_TEMPLATE.format(footer=_prepare(ana.footer, capture, source_url)),
        "front-page.php": "<?php get_header(); ?>\n"
        + _prepare(ana.main, capture, source_url)
        + "\n<?php get_footer(); ?>\n",
        "woocommerce.php": _WOOCOMMERCE,
        "page.php": _PAGE,
        "index.php": _PAGE,
    }
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
    return ThemeFiles(folder, tuple(sorted(dosyalar)))

"""Mağaza sayfalarının (liste, ürün, sepet, ödeme) stili: kaynak sitenin ölçülerinden üretilir.

Kopya tema ana sayfayı kaynaktan birebir alır; mağaza sayfalarını ise WooCommerce kendi
şablonlarıyla çizer. Ölçüldü (4 Ekim, kabul koşusu): o sayfalar WooCommerce'in varsayılan
görünümünde kaldı — mavi bağlantı, zeytin yeşili fiyat, mor düğme; kaynağın yazı tipi ve
renkleri hiç taşınmadı. Burada kaynak sayfanın ÖLÇÜLEN değerleri (yazı tipi, metin ve fiyat
rengi, düğme, ürün kartı oranı, kap genişliği) WooCommerce işaretlemesine uygulanır.
Değer ölçülemediyse nötr bir varsayılan kullanılır; siteye özel hiçbir şey içermez.
"""

# ruff: noqa: E501 — CSS şablonu satır satır okunur; kural başına bir satır korunur.
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: Ölçüm yoksa kullanılan nötr değerler (koyu metin, beyaz zemin, 4:5 kart).
FALLBACK_TEXT = "#111111"
FALLBACK_MUTED = "#6b6b6b"
FALLBACK_BACKGROUND = "#ffffff"
FALLBACK_FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
FALLBACK_RATIO = (4, 5)
MIN_COLUMNS, MAX_COLUMNS = 2, 6
DEFAULT_COLUMNS = 4
#: Bu kadar öğeden az tekrar eden bileşen "ürün kartı" sayılmaz.
MIN_CARD_REPEATS = 4

_RGB = re.compile(r"rgba?\(([^)]+)\)")
_PX = re.compile(r"(-?\d+(?:\.\d+)?)px")


@dataclass(frozen=True, slots=True)
class StoreTokens:
    """Kaynak sayfadan çıkarılan, mağaza stiline giren değerler."""

    body_font: str
    heading_font: str
    heading_transform: str
    text: str
    muted: str
    background: str
    line: str
    price_color: str
    price_size: str
    price_weight: str
    button_background: str
    button_color: str
    button_radius: str
    card_ratio: tuple[int, int]
    columns: int
    container: str
    header_strip: str


def _channels(color: str) -> tuple[float, float, float, float] | None:
    match = _RGB.search(color)
    if match is None:
        return None
    parts = [part.strip() for part in match.group(1).replace("/", ",").split(",")]
    try:
        numbers = [float(part.rstrip("%")) for part in parts if part]
    except ValueError:
        return None
    if len(numbers) < 3:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3] if len(numbers) > 3 else 1.0


def _luminance(color: str) -> float | None:
    channels = _channels(color)
    if channels is None:
        return None
    red, green, blue, _ = channels
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255


def _is_dark(color: str) -> bool:
    luminance = _luminance(color)
    return luminance is not None and luminance < 0.2


def _opaque(color: str) -> bool:
    channels = _channels(color)
    return channels is not None and channels[3] >= 0.5


def _values(items: object) -> list[str]:
    if not isinstance(items, Sequence) or isinstance(items, str):
        return []
    return [str(item["value"]) for item in items if isinstance(item, Mapping) and "value" in item]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _font_stack(name: str) -> str:
    cleaned = name.strip().strip("\"'")
    if not cleaned:
        return FALLBACK_FONT
    return cleaned if "," in cleaned else f"'{cleaned}', {FALLBACK_FONT}"


def _pixels(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = _PX.search(str(value))
    return float(match.group(1)) if match else None


def _product_card(page: Mapping[str, Any]) -> Mapping[str, Any]:
    """En çok tekrar eden, görseli ölçülmüş bileşen: ürün kartı."""
    components = page.get("components")
    if not isinstance(components, Sequence):
        return {}
    cards = [
        item
        for item in components
        if isinstance(item, Mapping)
        and isinstance(item.get("image"), Mapping)
        and int(item.get("count") or 0) >= MIN_CARD_REPEATS
    ]
    return max(cards, key=lambda item: int(item.get("count") or 0), default={})


def _ratio(card: Mapping[str, Any]) -> tuple[int, int]:
    image = _mapping(card.get("image"))
    width, height = _pixels(image.get("width")), _pixels(image.get("height"))
    if not width or not height or width < 40 or height < 40:
        return FALLBACK_RATIO
    return round(width), round(height)


def _columns(card: Mapping[str, Any], container: float | None) -> int:
    width = _pixels(_mapping(card.get("style")).get("width"))
    if not width or not container:
        return DEFAULT_COLUMNS
    return max(MIN_COLUMNS, min(MAX_COLUMNS, round(container / width)))


def _filled_button(page: Mapping[str, Any]) -> Mapping[str, Any]:
    """Dolgulu (zemini opak) ve en çok kullanılan düğme; yoksa boş."""
    buttons = page.get("buttons")
    if not isinstance(buttons, Sequence):
        return {}
    filled = [
        item
        for item in buttons
        if isinstance(item, Mapping) and _opaque(str(item.get("background", "")))
    ]
    return max(filled, key=lambda item: int(item.get("uses") or 0), default={})


def store_tokens(page: Mapping[str, Any]) -> StoreTokens:
    """Ölçüm raporunun bir sayfasından mağaza değerlerini çıkar; eksik olan varsayılana düşer."""
    fonts = _values(_mapping(page.get("fonts")).get("used"))
    scale = _mapping(page.get("scale"))
    heading = _mapping(scale.get("h1")) or _mapping(scale.get("h2"))
    colors = _mapping(page.get("colors"))
    texts = [c for c in _values(colors.get("text")) if _luminance(c) is not None]
    dark_texts = [c for c in texts if (_luminance(c) or 0) < 0.45 and _opaque(c)]
    grey_texts = [c for c in texts if 0.45 <= (_luminance(c) or 0) < 0.8]
    backgrounds = [c for c in _values(colors.get("background")) if _opaque(c)]
    light = [c for c in backgrounds if (_luminance(c) or 0) > 0.85]
    dark = [c for c in backgrounds if _is_dark(c)]
    text = dark_texts[0] if dark_texts else FALLBACK_TEXT
    price = _mapping(next(iter(page.get("prices") or []), {})).get("style")
    price_style = _mapping(price)
    button = _filled_button(page)
    card = _product_card(page)
    layout = _mapping(page.get("layout"))
    container = next(iter(_values(layout.get("container"))), "")
    container_px = _pixels(container) or _pixels(layout.get("viewport"))
    body_font = _font_stack(fonts[0]) if fonts else FALLBACK_FONT
    return StoreTokens(
        body_font=body_font,
        heading_font=_font_stack(str(heading.get("family", ""))) if heading else body_font,
        heading_transform=str(heading.get("transform") or "none"),
        text=text,
        muted=grey_texts[0] if grey_texts else FALLBACK_MUTED,
        background=light[0] if light else FALLBACK_BACKGROUND,
        line="rgba(0, 0, 0, 0.12)",
        price_color=str(price_style.get("color") or text),
        price_size=str(price_style.get("size") or "14px"),
        price_weight=str(price_style.get("weight") or "400"),
        button_background=str(button.get("background") or (dark[0] if dark else text)),
        button_color=str(button.get("color") or "#ffffff"),
        button_radius=str(
            button.get("radius") or _mapping(card.get("style")).get("radius") or "0px"
        ),
        card_ratio=_ratio(card),
        columns=_columns(card, container_px),
        container=container if _pixels(container) else "1280px",
        header_strip=dark[0] if dark else text,
    )


_TEMPLATE = """
/* --- Mağaza sayfaları: kaynak sitenin ölçülerinden üretildi (woo_store_css.py) --- */
.kopya-woocommerce, .kopya-sayfa {{
  background: {background}; color: {text}; font-family: {body_font};
  margin: 0 auto; max-width: {container}; padding-bottom: 64px;
  padding-left: 16px; padding-right: 16px;
}}
.kopya-woocommerce a, .kopya-sayfa a {{ color: inherit; text-decoration: none; }}
.kopya-woocommerce h1, .kopya-woocommerce h2, .kopya-sayfa h1, .kopya-sayfa h2 {{
  color: {text}; font-family: {heading_font}; font-weight: 500; letter-spacing: 0.01em;
  text-transform: {heading_transform};
}}
.kopya-woocommerce h1, .kopya-sayfa h1 {{ font-size: 28px; margin: 24px 0 16px; }}
.kopya-woocommerce .woocommerce-result-count,
.kopya-woocommerce .woocommerce-ordering select {{ color: {muted}; font: inherit; font-size: 13px; }}
.kopya-woocommerce .woocommerce-ordering select {{
  background: transparent; border: 1px solid {line}; border-radius: {button_radius};
  padding: 8px 10px;
}}
.kopya-woocommerce ul.products {{
  display: grid !important; gap: 32px 16px; grid-template-columns: repeat({columns}, minmax(0, 1fr));
  list-style: none; margin: 0 0 32px; padding: 0;
}}
.kopya-woocommerce ul.products::before, .kopya-woocommerce ul.products::after {{ display: none !important; }}
.kopya-woocommerce ul.products li.product {{
  display: flex; flex-direction: column; float: none !important; margin: 0 !important;
  text-align: left; width: auto !important;
}}
.kopya-woocommerce ul.products li.product > a:first-of-type {{ flex: 1 1 auto; }}
.kopya-woocommerce ul.products li.product a img {{
  aspect-ratio: {ratio_w} / {ratio_h}; display: block; height: auto; margin: 0 0 12px;
  object-fit: cover; width: 100%;
}}
.kopya-woocommerce ul.products li.product .woocommerce-loop-product__title {{
  color: {text}; font-family: {body_font}; font-size: 14px; font-weight: 400;
  line-height: 1.35; padding: 0 0 4px; text-transform: none;
}}
.kopya-woocommerce .price, .kopya-woocommerce ul.products li.product .price {{
  color: {price_color} !important; font-size: {price_size}; font-weight: {price_weight};
}}
.kopya-woocommerce .price del {{ color: {muted}; }}
.kopya-woocommerce .price ins {{ text-decoration: none; }}
.kopya-woocommerce .button, .kopya-woocommerce button.button, .kopya-woocommerce a.button,
.kopya-woocommerce input.button, .kopya-woocommerce #place_order,
.kopya-sayfa .button, .kopya-sayfa button.button, .kopya-sayfa a.button,
.kopya-sayfa .wc-block-components-button, .kopya-sayfa #place_order {{
  background: {button_background} !important; border: 0; border-radius: {button_radius};
  color: {button_color} !important; cursor: pointer; display: inline-block;
  font-family: {heading_font}; font-size: 14px; font-weight: 500; letter-spacing: 0.02em;
  line-height: 1.2; padding: 13px 22px; text-transform: {heading_transform};
  transition: opacity 150ms ease;
}}
.kopya-woocommerce .button:hover, .kopya-sayfa .button:hover,
.kopya-sayfa .wc-block-components-button:hover {{ opacity: 0.85; }}
.kopya-woocommerce .button:focus-visible, .kopya-sayfa .button:focus-visible {{
  outline: 2px solid {text}; outline-offset: 2px;
}}
.kopya-woocommerce ul.products li.product .button {{
  align-self: flex-start; margin-top: 10px; padding: 10px 16px;
}}
.kopya-woocommerce div.product {{
  align-items: start; display: grid; gap: 24px 48px; margin-top: 24px;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
}}
.kopya-woocommerce div.product div.images, .kopya-woocommerce div.product div.summary {{
  float: none !important; margin: 0; width: auto !important;
}}
.kopya-woocommerce div.product div.images img {{ display: block; height: auto; width: 100%; }}
.kopya-woocommerce div.product .product_title {{ font-size: 28px; line-height: 1.15; margin: 8px 0 12px; }}
.kopya-woocommerce div.product p.price {{ font-size: 20px; margin: 0 0 20px; }}
.kopya-woocommerce div.product form.cart {{ align-items: stretch; display: flex; gap: 10px; margin: 0 0 20px; }}
.kopya-woocommerce div.product form.cart .single_add_to_cart_button {{ flex: 1 1 auto; }}
.kopya-woocommerce div.product .product_meta {{ color: {muted}; font-size: 13px; }}
.kopya-woocommerce div.product .woocommerce-tabs, .kopya-woocommerce div.product .related,
.kopya-woocommerce div.product .upsells {{ grid-column: 1 / -1; }}
.kopya-woocommerce input[type="text"], .kopya-woocommerce input[type="email"],
.kopya-woocommerce input[type="tel"], .kopya-woocommerce input[type="number"],
.kopya-woocommerce input[type="password"], .kopya-woocommerce select, .kopya-woocommerce textarea,
.kopya-sayfa input[type="text"], .kopya-sayfa input[type="email"], .kopya-sayfa input[type="tel"],
.kopya-sayfa input[type="number"], .kopya-sayfa select, .kopya-sayfa textarea {{
  background: {background}; border: 1px solid {line}; border-radius: {button_radius};
  color: {text}; font: inherit; padding: 11px 12px;
}}
.kopya-woocommerce .quantity input.qty {{ text-align: center; width: 72px; }}
.kopya-woocommerce table.shop_table, .kopya-sayfa table.shop_table {{
  border: 0; border-collapse: collapse; width: 100%;
}}
.kopya-woocommerce table.shop_table th, .kopya-woocommerce table.shop_table td,
.kopya-sayfa table.shop_table th, .kopya-sayfa table.shop_table td {{
  border: 0; border-bottom: 1px solid {line}; padding: 14px 8px; text-align: left;
}}
.kopya-woocommerce .woocommerce-message, .kopya-woocommerce .woocommerce-info,
.kopya-woocommerce .woocommerce-error, .kopya-sayfa .woocommerce-message,
.kopya-sayfa .woocommerce-info, .kopya-sayfa .woocommerce-error {{
  background: rgba(0, 0, 0, 0.04); border: 0; border-left: 3px solid {text}; color: {text};
  list-style: none; margin: 0 0 20px; padding: 14px 16px;
}}
.kopya-woocommerce .woocommerce-pagination ul {{ border: 0; display: flex; gap: 6px; justify-content: center; }}
.kopya-woocommerce .woocommerce-pagination ul li {{ border: 0; }}
.kopya-woocommerce .woocommerce-pagination .page-numbers {{
  border: 1px solid {line}; color: {text}; display: block; min-width: 38px; padding: 9px 12px;
  text-align: center;
}}
.kopya-woocommerce .woocommerce-pagination .page-numbers.current {{
  background: {button_background}; color: {button_color};
}}
@media (max-width: 1024px) {{
  .kopya-woocommerce ul.products {{ grid-template-columns: repeat({columns_medium}, minmax(0, 1fr)); }}
}}
@media (max-width: 720px) {{
  .kopya-woocommerce ul.products {{ gap: 24px 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .kopya-woocommerce div.product {{ grid-template-columns: minmax(0, 1fr); }}
}}
"""

_HEADER_STRIP = """
/* Başlık ana sayfada görselin üstünde saydamdır; iç sayfalarda arkasına dolgu gerekir. */
body:not(.home)::before {{
  background: {header_strip}; content: ""; height: {offset}px; left: 0; position: fixed;
  right: 0; top: 0; z-index: 0;
}}
"""


def store_css(page: Mapping[str, Any] | None, header_offset: int = 0) -> str:
    """Mağaza sayfalarının CSS'i. `page`: ölçüm raporundaki ana sayfa (yoksa varsayılanlar)."""
    tokens = store_tokens(page or {})
    css = _TEMPLATE.format(
        body_font=tokens.body_font,
        heading_font=tokens.heading_font,
        heading_transform=tokens.heading_transform,
        text=tokens.text,
        muted=tokens.muted,
        background=tokens.background,
        line=tokens.line,
        price_color=tokens.price_color,
        price_size=tokens.price_size,
        price_weight=tokens.price_weight,
        button_background=tokens.button_background,
        button_color=tokens.button_color,
        button_radius=tokens.button_radius,
        ratio_w=tokens.card_ratio[0],
        ratio_h=tokens.card_ratio[1],
        columns=tokens.columns,
        columns_medium=max(MIN_COLUMNS, min(3, tokens.columns)),
        container=tokens.container,
    )
    if header_offset > 0:
        css += _HEADER_STRIP.format(header_strip=tokens.header_strip, offset=header_offset)
    return css

"""Mağaza stili kaynak sitenin ölçülerinden üretilir; ölçüm yoksa nötr varsayılana düşer."""

from __future__ import annotations

from fusion_cli.tools.woo_store_css import (
    DEFAULT_COLUMNS,
    FALLBACK_RATIO,
    FALLBACK_TEXT,
    store_css,
    store_tokens,
)

OLCUM = {
    "fonts": {"used": [{"value": "Inter", "weight": 9568}, {"value": "Oswald", "weight": 251}]},
    "scale": {"h2": {"family": "Oswald, sans-serif", "transform": "uppercase"}},
    "colors": {
        "text": [
            {"value": "rgba(0, 0, 0, 0.87)", "weight": 4568},
            {"value": "rgb(159, 159, 159)", "weight": 1875},
            {"value": "rgb(255, 255, 255)", "weight": 321},
        ],
        "background": [
            {"value": "rgb(255, 255, 255)", "weight": 14918},
            {"value": "rgb(0, 0, 0)", "weight": 1815},
            {"value": "rgba(0, 0, 0, 0.22)", "weight": 900},
        ],
    },
    "prices": [
        {"text": "3.899,00 TL",
         "style": {"size": "12px", "weight": "400", "color": "rgb(23, 22, 32)"}}
    ],
    "buttons": [
        {"background": "rgba(0, 0, 0, 0)", "color": "rgb(17, 17, 17)", "radius": "0px", "uses": 64},
        {"background": "rgb(23, 22, 32)", "color": "rgb(255, 255, 255)", "radius": "2px",
         "uses": 3},
    ],
    "components": [
        {"count": 136, "style": {"width": 250, "height": 399, "radius": "0px"},
         "image": {"width": 250, "height": 300}},
        {"count": 2, "style": {"width": 900}, "image": {"width": 900, "height": 400}},
    ],
    "layout": {"viewport": 1440, "container": [{"value": "1408px", "weight": 1}]},
}  # fmt: skip


def test_olculen_degerler_magaza_degerlerine_doner():
    tokens = store_tokens(OLCUM)

    assert tokens.body_font.startswith("'Inter'")
    assert tokens.heading_font == "Oswald, sans-serif" and tokens.heading_transform == "uppercase"
    assert tokens.text == "rgba(0, 0, 0, 0.87)" and tokens.muted == "rgb(159, 159, 159)"
    assert tokens.price_color == "rgb(23, 22, 32)" and tokens.price_size == "12px"
    assert tokens.button_background == "rgb(23, 22, 32)" and tokens.button_radius == "2px"
    assert tokens.card_ratio == (250, 300)
    assert tokens.columns == 6 and tokens.container == "1408px"
    assert tokens.header_strip == "rgb(0, 0, 0)"


def test_css_woocommerce_varsayilan_gorunumunu_kaynak_degerleriyle_ezer():
    css = store_css(OLCUM, header_offset=60)

    assert "font-family: 'Inter'" in css and "Oswald, sans-serif" in css
    assert "aspect-ratio: 250 / 300" in css
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in css
    assert "background: rgb(23, 22, 32) !important" in css
    assert "color: rgb(23, 22, 32) !important" in css
    assert "color: inherit; text-decoration: none" in css
    assert "body:not(.home)::before" in css and "height: 60px" in css
    assert "{" in css and "{{" not in css and "}}" not in css


def test_olcum_yoksa_notr_varsayilanlar_ve_baslik_seridi_yok():
    tokens = store_tokens({})
    css = store_css(None)

    assert tokens.text == FALLBACK_TEXT and tokens.card_ratio == FALLBACK_RATIO
    assert tokens.columns == DEFAULT_COLUMNS and tokens.button_color == "#ffffff"
    assert "body:not(.home)::before" not in css
    assert f"aspect-ratio: {FALLBACK_RATIO[0]} / {FALLBACK_RATIO[1]}" in css


def test_saydam_dugme_ve_tek_tuk_bilesen_secilmez():
    olcum = {
        "buttons": [{"background": "rgba(0, 0, 0, 0)", "color": "rgb(1, 1, 1)", "uses": 99}],
        "components": [
            {"count": 2, "style": {"width": 300}, "image": {"width": 300, "height": 100}}
        ],
        "colors": {"text": [{"value": "rgb(20, 20, 20)", "weight": 5}]},
    }

    tokens = store_tokens(olcum)

    assert tokens.button_background == "rgb(20, 20, 20)" and tokens.button_color == "#ffffff"
    assert tokens.card_ratio == FALLBACK_RATIO


def test_bozuk_olcum_cokmeye_yol_acmaz():
    assert store_css({"fonts": "x", "colors": [], "components": [None, 3], "prices": [7]})

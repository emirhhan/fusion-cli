"""Doğrulanmış kaynak varyantları için inert tema parçaları ve yerel runtime."""

from __future__ import annotations

import html
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .site_capture import CapturedPage, SiteCapture, localize

RUNTIME_ASSET = Path(__file__).with_name("assets") / "theme_responsive.js"


@dataclass(frozen=True, slots=True)
class ResponsiveTheme:
    """Tek etkin DOM/CSS için üretilen parçalar; kaynak JS'i taklit edilmez."""

    header: str
    main: str
    footer: str
    runtime: str


def _region(name: str, wide: str, narrow: str, query: str) -> str:
    """İlk görünüm masaüstü; diğer DOM'lar template içinde erişilemez/inerttir."""
    return (
        f'<div data-fusion-region="{name}" data-fusion-active="wide" style="display:contents">'
        f"{wide}</div>"
        f'<template data-fusion-part="{name}" data-fusion-variant="wide">{wide}</template>'
        f'<template data-fusion-part="{name}" data-fusion-variant="narrow" '
        f'data-fusion-query="{html.escape(query, quote=True)}">{narrow}</template>'
    )


def build_responsive_theme(
    page: CapturedPage,
    capture: SiteCapture,
    prepare: Callable[[str], str],
    asset_prefix: str,
) -> ResponsiveTheme | None:
    """Yalnız doğrulanmış ana varyantın header/main/footer parçalarını aktar."""
    narrow = next((variant for variant in page.variants if variant.media_query), None)
    if narrow is None or not page.variants:
        return None
    wide = page.variants[0]
    query = narrow.media_query
    assert query is not None
    shared = capture.css.replace(wide.css, "")
    css_templates = []
    for name, variant in (("wide", wide), ("narrow", narrow)):
        css = localize(shared + "\n" + variant.css, capture.assets, asset_prefix)
        css = css.replace("</", "<\\/")
        css_templates.append(
            f'<template data-fusion-css="{name}" data-fusion-offset="{variant.header_offset}">'
            f"<style>{css}</style></template>"
        )
    return ResponsiveTheme(
        header=_region("header", prepare(wide.header), prepare(narrow.header), query)
        + "".join(css_templates),
        main=_region("main", prepare(wide.main), prepare(narrow.main), query),
        footer=_region("footer", prepare(wide.footer), prepare(narrow.footer), query),
        runtime=RUNTIME_ASSET.read_text(encoding="utf-8"),
    )

"""Doğrulanmış kaynak varyantları için inert tema parçaları ve yerel runtime."""

from __future__ import annotations

import html
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .site_capture import CapturedPage, SiteCapture, localize
from .theme_region import ThemeRegion, theme_regions

RUNTIME_ASSET = Path(__file__).with_name("assets") / "theme_responsive.js"


@dataclass(frozen=True, slots=True)
class ResponsiveTheme:
    """Tek etkin DOM/CSS için üretilen parçalar; kaynak JS'i taklit edilmez."""

    header: str
    main: str
    footer: str
    runtime: str


def _region(name: str, regions: tuple[ThemeRegion, ...], prepare: Callable[[str], str]) -> str:
    """Diğer DOM'lar inert kalır; koşullar yalnız kaynak sorgularından gelir."""
    wide = regions[-1]
    parts = [
        f'<div data-fusion-region="{name}" data-fusion-active="wide" style="display:contents">'
        f"{prepare(getattr(wide.variant, name))}</div>"
    ]
    for region in regions:
        predicates = json.dumps(
            [{"query": item.query, "matches": item.matches} for item in region.predicates]
        )
        parts.append(
            f'<template data-fusion-part="{name}" data-fusion-variant="{region.name}" '
            f'data-fusion-conditions="{html.escape(predicates, quote=True)}" '
            f'data-fusion-query="{html.escape(region.predicates[0].query, quote=True)}">'
            f"{prepare(getattr(region.variant, name))}</template>"
        )
    return "".join(parts)


def build_responsive_theme(
    page: CapturedPage,
    capture: SiteCapture,
    prepare: Callable[[str], str],
    asset_prefix: str,
) -> ResponsiveTheme | None:
    """Yalnız doğrulanmış ana varyantın header/main/footer parçalarını aktar."""
    regions = theme_regions(page)
    if not regions:
        return None
    wide = regions[-1].variant
    shared = capture.css.replace(wide.css, "")
    css_templates = []
    for region in regions:
        name, variant = region.name, region.variant
        css = localize(shared + "\n" + variant.css, capture.assets, asset_prefix)
        css = css.replace("</", "<\\/")
        css_templates.append(
            f'<template data-fusion-css="{name}" data-fusion-offset="{variant.header_offset}">'
            f"<style>{css}</style></template>"
        )
    return ResponsiveTheme(
        header=_region("header", regions, prepare) + "".join(css_templates),
        main=_region("main", regions, prepare),
        footer=_region("footer", regions, prepare),
        runtime=RUNTIME_ASSET.read_text(encoding="utf-8"),
    )

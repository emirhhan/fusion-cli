"""Yakalanan viewportlar ve kaynaktan doğrulanabilen genişlik koşulları.

İlk faz yalnız yakalama sözleşmesidir; tema halen ana varyantı kullanır.
CSS dışı JavaScript eşikleri tahmin edilmez.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

_WIDTH_QUERY = re.compile(r"^(?:screen\s+and\s+)?\((min|max)-width\s*:\s*(\d+)px\)$", re.I)


@dataclass(frozen=True, slots=True)
class WidthCondition:
    """Kaynak CSS'ten gelen tek genişlik koşulu; piksel eşiği uydurulmaz."""

    query: str
    boundary: int
    is_maximum: bool


@dataclass(frozen=True, slots=True)
class CapturedVariant:
    """Bir viewportun DOM, CSS ve görünür yapı kanıtı."""

    width: int
    height: int
    header: str
    main: str
    footer: str
    header_offset: int
    css: str
    signature: str
    media_conditions: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    media_query: str | None = None


@dataclass(frozen=True, slots=True)
class ResponsiveCapture:
    """Viewportlar ve henüz desteklenmeyen geçişlerin açık raporu."""

    variants: tuple[CapturedVariant, ...]
    problems: tuple[str, ...]


def width_conditions(queries: tuple[str, ...]) -> tuple[WidthCondition, ...]:
    """Yalnız tek px genişlik koşulunu kabul et; birleşik sorguyu daraltma."""
    conditions = []
    for query in dict.fromkeys(queries):
        match = _WIDTH_QUERY.fullmatch(query.strip())
        if match:
            conditions.append(WidthCondition(query, int(match[2]), match[1].lower() == "max"))
    return tuple(conditions)


async def _validated_conditions(
    wide: CapturedVariant,
    narrow: CapturedVariant,
    conditions: tuple[WidthCondition, ...],
    capture: Callable[[int, int], Awaitable[CapturedVariant]],
) -> list[WidthCondition]:
    """Adayları aynı yükseklikte exact sınırın iki yanında ölç."""
    candidates = [item for item in conditions if narrow.width < item.boundary < wide.width]
    validated = []
    for item in candidates:
        left_width = item.boundary if item.is_maximum else item.boundary - 1
        right_width = item.boundary + 1 if item.is_maximum else item.boundary
        left = await capture(left_width, wide.height)
        right = await capture(right_width, wide.height)
        if (
            left.signature == narrow.signature
            and right.signature == wide.signature
            and left.signature != right.signature
        ):
            validated.append(item)
    return validated


async def verify_variants(
    variants: tuple[CapturedVariant, ...],
    capture: Callable[[int, int], Awaitable[CapturedVariant]],
) -> ResponsiveCapture:
    """Kaynak eşiğinin iki yanında aynı DOM geçişini yeniden gözlemle.

    Birden fazla geçiş veya CSS'te görünmeyen JavaScript koşulu tek eşiğe
    indirgenmez. Varyantlar yine saklanır, doğrulanmış medya sorgusu verilmez.
    """
    if len(variants) < 2:
        return ResponsiveCapture(variants, ())
    wide, narrow = variants[0], variants[-1]
    reference_height = wide.height
    if narrow.height != reference_height:
        same_height = await capture(narrow.width, reference_height)
        if same_height.signature != narrow.signature:
            return ResponsiveCapture(
                variants,
                (
                    "Viewport DOM farkı yükseklik değişiminden etkileniyor; "
                    "genişlik eşiği doğrulanmadı.",
                    "Viewport varyantları yakalandı; responsive tema aktarımı henüz uygulanmadı.",
                ),
            )
    queries = tuple(query for variant in variants for query in variant.media_conditions)
    conditions = width_conditions(queries)
    validated = await _validated_conditions(wide, narrow, conditions, capture)
    # Tamamlayıcı min/max sorguları aynı geçişi anlatabilir; açık dar koşulu koru.
    maxima = {item.boundary for item in validated if item.is_maximum}
    validated = [item for item in validated if item.is_maximum or item.boundary - 1 not in maxima]
    problems = []
    if len(validated) == 1:
        condition = validated[0]
        query = (
            condition.query
            if condition.is_maximum
            else f"not all and (min-width: {condition.boundary}px)"
        )
        variants = (*variants[:-1], replace(narrow, media_query=query))
    elif wide.signature != narrow.signature:
        problems.append(
            "Viewport DOM geçişi tek kaynak CSS genişlik koşuluyla doğrulanamadı; "
            "responsive eşik tahmin edilmedi."
        )
    unsupported = [
        query
        for query in queries
        if "width" in query.lower() and query not in {item.query for item in conditions}
    ]
    if unsupported:
        problems.append(
            "Birleşik, aralık veya px dışı kaynak medya koşulu bu yakalama fazında desteklenmiyor."
        )
    problems.append(
        "Viewport varyantları yakalandı; responsive tema aktarımı henüz uygulanmadı, "
        "mevcut tema ana varyantı kullanır."
    )
    return ResponsiveCapture(variants, tuple(problems))

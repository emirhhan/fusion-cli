"""Doğrulanmış kaynak geçişlerinden tema seçim bölgeleri üret; eşik uydurma."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from .site_capture import CapturedPage
from .site_responsive import CapturedTransition, CapturedVariant, width_conditions


@dataclass(frozen=True, slots=True)
class SourcePredicate:
    """Kaynak medya sorgusunun bir bölgedeki doğrulanmış doğru/yanlış yönü."""

    query: str
    matches: bool


@dataclass(frozen=True, slots=True)
class ThemeRegion:
    """Tek DOM/CSS gözlemi ve bölgeyi seçen kaynak sorguları."""

    name: str
    variant: CapturedVariant
    predicates: tuple[SourcePredicate, ...]


def _valid_transition(item: CapturedTransition) -> bool:
    """Sorgu yönü ve exact sınırın gerçekten soldan sağa geçiş anlattığını doğrula."""
    query = item.query.strip().lower()
    is_negated = query.startswith("not all and ")
    conditions = width_conditions((query.removeprefix("not all and "),))
    if len(conditions) != 1:
        return False
    condition = conditions[0]
    boundary = condition.boundary if condition.is_maximum else condition.boundary - 1
    return (
        condition.is_maximum != is_negated
        and item.left.width == boundary
        and item.right.width == boundary + 1
        and item.left.height == item.right.height
        and item.left.signature != item.right.signature
    )


def theme_regions(page: CapturedPage) -> tuple[ThemeRegion, ...]:
    """Bağlı kaynak geçiş zinciri; yalnız ikili eski sözleşme geriye uyumludur."""
    if not page.variants:
        return ()
    wide, narrow = page.variants[0], page.variants[-1]
    transitions = page.transitions
    if len(transitions) < 2:
        if narrow.media_query is None:
            return ()
        return (
            ThemeRegion("narrow", narrow, (SourcePredicate(narrow.media_query, True),)),
            ThemeRegion("wide", wide, (SourcePredicate(narrow.media_query, False),)),
        )
    if (
        not all(_valid_transition(item) for item in transitions)
        or transitions[0].left.signature != narrow.signature
        or transitions[-1].right.signature != wide.signature
        or any(item.left.height != wide.height for item in transitions)
    ):
        return ()
    for before, after in pairwise(transitions):
        if (
            before.right.width >= after.right.width
            or before.right.signature != after.left.signature
        ):
            return ()
    variants = (narrow, *[item.right for item in transitions[:-1]], wide)
    return tuple(
        ThemeRegion(
            "wide" if index == len(transitions) else f"region-{index}",
            variant,
            tuple(
                SourcePredicate(item.query, position >= index)
                for position, item in enumerate(transitions)
            ),
        )
        for index, variant in enumerate(variants)
    )

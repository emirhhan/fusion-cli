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
class CapturedTransition:
    """Kaynaktaki exact genişlik sınırının aynı yükseklikte iki yanı."""

    query: str
    left: CapturedVariant
    right: CapturedVariant
    source_queries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResponsiveCapture:
    """Viewportlar ve henüz desteklenmeyen geçişlerin açık raporu."""

    variants: tuple[CapturedVariant, ...]
    problems: tuple[str, ...]
    transitions: tuple[CapturedTransition, ...] = ()


def captured_variants(
    variants: tuple[CapturedVariant, ...], transitions: tuple[CapturedTransition, ...]
) -> tuple[CapturedVariant, ...]:
    """İlk viewportlar ve exact sınır kanıtları; geometriyi signature ile birleştirme."""
    observations = dict.fromkeys((item.width, item.height) for item in variants)
    values = {(item.width, item.height): item for item in variants}
    for transition in transitions:
        for item in (transition.left, transition.right):
            key = (item.width, item.height)
            observations.setdefault(key, None)
            values.setdefault(key, item)
    return tuple(values[key] for key in observations)


def width_conditions(queries: tuple[str, ...]) -> tuple[WidthCondition, ...]:
    """Yalnız tek px genişlik koşulunu kabul et; birleşik sorguyu daraltma."""
    conditions = []
    for query in dict.fromkeys(queries):
        match = _WIDTH_QUERY.fullmatch(query.strip())
        if match:
            conditions.append(WidthCondition(query, int(match[2]), match[1].lower() == "max"))
    return tuple(conditions)


@dataclass(frozen=True, slots=True)
class TransitionValidation:
    """Doğrulanan yerel geçişler ve aynı viewportta kararsız gözlem sınırı."""

    transitions: tuple[CapturedTransition, ...]
    has_unstable_capture: bool


async def _stable_capture(
    variant: CapturedVariant,
    capture: Callable[[int, int], Awaitable[CapturedVariant]],
    stability: dict[tuple[int, int], bool],
) -> bool:
    """Değişimi kabul etmeden aynı viewportu bağımsız fresh context ile karşılaştır."""
    key = (variant.width, variant.height)
    if key not in stability:
        repeat = await capture(*key)
        stability[key] = repeat.signature == variant.signature
    return stability[key]


async def _validated_transitions(
    wide: CapturedVariant,
    narrow: CapturedVariant,
    conditions: tuple[WidthCondition, ...],
    capture: Callable[[int, int], Awaitable[CapturedVariant]],
    repeat_capture: Callable[[int, int], Awaitable[CapturedVariant]],
) -> TransitionValidation:
    """Yerel geçişleri ölç; aynı exact sınırın tamamlayıcı sorgularını birleştir."""
    cache = {(item.width, item.height): item for item in (wide, narrow)}
    transitions: dict[tuple[int, int], CapturedTransition] = {}
    stability: dict[tuple[int, int], bool] = {}
    ordered = sorted(conditions, key=lambda item: (item.boundary, not item.is_maximum))
    for item in ordered:
        left_width = item.boundary if item.is_maximum else item.boundary - 1
        right_width = left_width + 1
        if not narrow.width <= left_width < right_width <= wide.width:
            continue
        pair = (left_width, right_width)
        for width in pair:
            key = (width, wide.height)
            if key not in cache:
                cache[key] = await capture(width, wide.height)
        left, right = (cache[(width, wide.height)] for width in pair)
        if left.signature == right.signature:
            continue
        is_left_stable = await _stable_capture(left, repeat_capture, stability)
        is_right_stable = await _stable_capture(right, repeat_capture, stability)
        if not is_left_stable or not is_right_stable:
            continue
        existing = transitions.get(pair)
        if existing:
            transitions[pair] = replace(
                existing, source_queries=(*existing.source_queries, item.query)
            )
        else:
            query = item.query if item.is_maximum else f"not all and (min-width: {item.boundary}px)"
            transitions[pair] = CapturedTransition(query, left, right, (item.query,))
    return TransitionValidation(
        tuple(transitions[pair] for pair in sorted(transitions)),
        any(not is_stable for is_stable in stability.values()),
    )


def _assign_legacy_query(
    variants: tuple[CapturedVariant, ...], transitions: tuple[CapturedTransition, ...]
) -> tuple[CapturedVariant, ...]:
    """İkili tema yalnız exact geçiş uç viewportları da açıklıyorsa kullanılabilir."""
    if len(transitions) != 1:
        return variants
    transition = transitions[0]
    if (
        transition.left.signature != variants[-1].signature
        or transition.right.signature != variants[0].signature
    ):
        return variants
    return (*variants[:-1], replace(variants[-1], media_query=transition.query))


def _cached_capture(
    variants: tuple[CapturedVariant, ...],
    capture: Callable[[int, int], Awaitable[CapturedVariant]],
) -> Callable[[int, int], Awaitable[CapturedVariant]]:
    """İlk gözlemi önbellekle; kararlılık tekrarı bu önbelleğin dışında yürütülür."""
    cache = {(item.width, item.height): item for item in variants}

    async def cached(width: int, height: int) -> CapturedVariant:
        key = (width, height)
        if key not in cache:
            cache[key] = await capture(width, height)
        return cache[key]

    return cached


async def verify_variants(
    variants: tuple[CapturedVariant, ...],
    capture: Callable[[int, int], Awaitable[CapturedVariant]],
) -> ResponsiveCapture:
    """Kaynak eşiğinin iki yanında aynı DOM geçişini yeniden gözlemle.

    Birden fazla yerel geçiş ayrı kanıt olarak saklanır; tek eşiğe indirgenmez.
    CSS dışında kalan JavaScript koşulu veya çoklu tema başarısı iddia edilmez.
    """
    if len(variants) < 2:
        return ResponsiveCapture(variants, ())
    repeat_capture = capture
    capture = _cached_capture(variants, capture)
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
    validation = await _validated_transitions(wide, narrow, conditions, capture, repeat_capture)
    transitions = validation.transitions
    variants = _assign_legacy_query(variants, transitions)
    problems = []
    if validation.has_unstable_capture:
        problems.append(
            "Aynı viewport bağımsız yakalamada kararsız; bu fark kaynak CSS geçişi sayılmadı."
        )
    if len(transitions) > 1:
        problems.append(
            "Çoklu kaynak genişlik geçişleri yakalandı; çoklu bölge tema aktarımı desteklenmiyor."
        )
    elif variants[-1].media_query is None and wide.signature != narrow.signature:
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
    return ResponsiveCapture(variants, tuple(problems), transitions)

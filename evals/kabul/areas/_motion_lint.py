"""CSS/JS metninden hareket kalıplarını çıkaran saf ayrıştırıcı (tarayıcı gerekmez).

Ölçülenler: `@keyframes` adları, `transition` kalemleri, layout tetikleyen özelliklerin
(width, height, top, left, margin, padding...) animasyon/transition'da kullanımı ve
kullanılan easing çeşitleri. Düzenli ifade tabanlıdır; derleyici değildir ama
kabul fikstürlerinde ve tipik üretilmiş sayfalarda deterministik ölçer.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

#: Tam adıyla layout tetikleyen özellikler. `margin*` ve `padding*` önekle yakalanır.
LAYOUT_PROPERTIES = frozenset(
    {
        "width",
        "height",
        "top",
        "left",
        "right",
        "bottom",
        "inset",
        "min-width",
        "max-width",
        "min-height",
        "max-height",
    }
)
_LAYOUT_PREFIXES = ("margin", "padding")
_EASING_KEYWORDS = frozenset(
    {"ease", "ease-in", "ease-out", "ease-in-out", "linear", "step-start", "step-end"}
)

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_KEYFRAMES_HEAD = re.compile(r"@(?:-webkit-)?keyframes\s+([\w-]+)\s*\{", re.I)
_TRANSITION_DECL = re.compile(r"(?<![\w-])transition(?:-property)?\s*:\s*([^;}]+)", re.I)
_TIMING_DECL = re.compile(
    r"(?<![\w-])(?:transition|animation)(?:-timing-function)?\s*:\s*([^;}]+)", re.I
)
_PROPERTY_DECL = re.compile(r"(?<![\w-])([a-z-]+)\s*:", re.I)
_EASING_FUNCTION = re.compile(r"(?:cubic-bezier|steps|linear)\([^)]*\)", re.I)
_PARENTHESES = re.compile(r"\([^)]*\)")
_JS_EASING = re.compile(r"""\b(?:easing|ease)\s*:\s*["']([^"']+)["']""")
_REDUCED_MOTION = re.compile(r"prefers-reduced-motion", re.I)


@dataclass(frozen=True, slots=True)
class CssMotion:
    """CSS metninden çıkan hareket özeti."""

    keyframe_names: tuple[str, ...] = ()
    transition_count: int = 0
    layout_hits: tuple[str, ...] = ()
    easings: tuple[str, ...] = ()

    @property
    def pattern_count(self) -> int:
        return len(self.keyframe_names) + self.transition_count


def is_layout_property(name: str) -> bool:
    """Özellik adı layout tetikliyorsa doğru (ör. `margin-left`, `width`)."""
    lowered = name.strip().lower()
    return lowered in LAYOUT_PROPERTIES or lowered.startswith(_LAYOUT_PREFIXES)


def has_reduced_motion_query(text: str) -> bool:
    """`prefers-reduced-motion` sorgusu (CSS ya da `matchMedia`) geçiyor mu."""
    return _REDUCED_MOTION.search(text) is not None


def _balanced_block(text: str, start: int) -> str:
    """`start`, açılış süslü parantezinden hemen sonradır; eşleşen kapanışa dek metni ver."""
    depth = 1
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index]
    return text[start:]


def _iter_keyframes(css: str) -> Iterator[tuple[str, str]]:
    for match in _KEYFRAMES_HEAD.finditer(css):
        yield match.group(1), _balanced_block(css, match.end())


def split_top_level(value: str) -> list[str]:
    """Virgülle ayır ama parantez içindekilere (cubic-bezier) dokunma."""
    items: list[str] = []
    depth = 0
    current: list[str] = []
    for char in value:
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    items.append("".join(current).strip())
    return [item for item in items if item]


def _transition_items(css: str) -> list[str]:
    items: list[str] = []
    for match in _TRANSITION_DECL.finditer(css):
        value = match.group(1).strip()
        if value.lower() not in ("none", "initial", "unset"):
            items.extend(split_top_level(value))
    return items


def _layout_in_transitions(items: list[str]) -> list[str]:
    hits: list[str] = []
    for item in items:
        for token in _PARENTHESES.sub("", item).split():
            if is_layout_property(token):
                hits.append(f"transition:{token.lower()}")
    return hits


def _layout_in_keyframes(css: str) -> list[str]:
    hits: list[str] = []
    for name, body in _iter_keyframes(css):
        for match in _PROPERTY_DECL.finditer(body):
            if is_layout_property(match.group(1)):
                hits.append(f"@keyframes {name}:{match.group(1).lower()}")
    return hits


def _normalise_easing(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _css_easings(css: str) -> set[str]:
    found: set[str] = set()
    for match in _TIMING_DECL.finditer(css):
        value = match.group(1)
        found.update(_normalise_easing(fn) for fn in _EASING_FUNCTION.findall(value))
        for token in _PARENTHESES.sub("", value).replace(",", " ").split():
            if token.lower() in _EASING_KEYWORDS:
                found.add(token.lower())
    return found


_CUSTOM_PROPERTY = re.compile(r"(--[\w-]+)\s*:\s*([^;}]+)")
_VAR_USE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)")


def resolve_custom_properties(css: str) -> str:
    """`var(--ad)` kullanımlarını tanımlı değerle değiştir (tek düzey, ilk tanım).

    Ölçüldü (4 Ekim): easing `var(--ease)` ile verildiğinde sayım 0 çıkıyordu; değişken
    çözülmeden sayılan easing gerçeği yansıtmaz.
    """
    tanimlar: dict[str, str] = {}
    for ad, deger in _CUSTOM_PROPERTY.findall(css):
        tanimlar.setdefault(ad, deger.strip())
    return _VAR_USE.sub(lambda m: tanimlar.get(m.group(1), m.group(0)), css)


def analyse_css(css: str) -> CssMotion:
    """CSS metnindeki hareket kalıplarını, layout ihlallerini ve easing'leri çıkar."""
    clean = resolve_custom_properties(_COMMENT.sub("", css))
    names = tuple(dict.fromkeys(name for name, _ in _iter_keyframes(clean)))
    items = _transition_items(clean)
    hits = _layout_in_transitions(items) + _layout_in_keyframes(clean)
    return CssMotion(
        keyframe_names=names,
        transition_count=len(items),
        layout_hits=tuple(dict.fromkeys(hits)),
        easings=tuple(sorted(_css_easings(clean))),
    )


def js_easings(js: str) -> tuple[str, ...]:
    """JS animasyon çağrılarında (`easing: '...'`, GSAP `ease:`) geçen easing adları."""
    return tuple(sorted({_normalise_easing(match) for match in _JS_EASING.findall(js)}))

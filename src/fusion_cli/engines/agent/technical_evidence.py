"""Kodla belirtilen teknik adlar için gerekli, tek başına yeterli olmayan metin kanıtı."""

from __future__ import annotations

import html
import re
from bisect import bisect_left
from collections.abc import Iterable, Mapping
from typing import NamedTuple

from .technical_markup import plain_markup, target_code_fragments

_COMPACT_PARTS = re.compile(r"(\s+|::|[._()=])")
_COMPACT_PUNCTUATION = frozenset({"::", ".", "_", "(", ")", "="})
_FLAG_START_SPACE = re.compile(r"(?<!\w)--\s+(?=[A-Za-z])")
_WORD_HYPHEN_SPACE = re.compile(r"(?<=[A-Za-z0-9])\s*-\s*(?=[A-Za-z0-9])")
_IDENTIFIER = r"[A-Za-z_][A-Za-z_0-9]*"
_QUALIFIED = re.compile(_IDENTIFIER + r"(?:(?:\.|::)" + _IDENTIFIER + r")+")
_CALL = re.compile(_IDENTIFIER + r"\(\)")
_SNAKE = re.compile(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z_0-9]+")
_ERROR_TYPE = re.compile(r"[A-Z][A-Za-z0-9]*(?:Error|Warning|Exception)")
_FLAG = re.compile(r"--[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*(?==|$)")
_FILE_SUFFIX = re.compile(
    r"\.(?:md|rst|txt|html?|json|ya?ml|csv|tsv|xml|toml|py|js|ts|css|png|jpe?g|pdf|zip)$", re.I
)
_AUTHORED_CONTEXT = re.compile(
    r"\b(?:example|illustration|variable|örne[ğgk]\w*|ornek\w*|değişken\w*|degisken\w*)\b", re.I
)
_DELIVERY_CONTEXT = re.compile(
    r"\b(?:filename|filepath|saved|written|path|dosya\s+adı|kaydet\w*|kayded\w*|yol\w*)\b", re.I
)
_CAMEL_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+")
_IMPORT_ALIAS = re.compile(
    r"(?:^|[;\n`]|[.]\s+)[ \t]*import[ \t]+(?P<module>"
    + _IDENTIFIER
    + r"(?:[ \t]*\.[ \t]*"
    + _IDENTIFIER
    + r")*)[ \t]+as[ \t]+(?P<alias>"
    + _IDENTIFIER
    + r")(?=$|[ \t\r\n;`,]|[.](?:\s|$))",
    re.M,
)
_AS_BINDING = re.compile(r"\bas[ \t]+(?P<alias>" + _IDENTIFIER + r")(?!\w)")
_ASSIGNMENT = re.compile(r"(?<![\w.])(?P<name>" + _IDENTIFIER + r")\s*(?::=|=(?!=))")


class _Markers(NamedTuple):
    starts: tuple[int, ...]
    ends: tuple[int, ...]


def _markers(pattern: re.Pattern[str], text: str) -> _Markers:
    matches = tuple(pattern.finditer(text))
    return _Markers(tuple(row.start() for row in matches), tuple(row.end() for row in matches))


def _contains_marker(markers: _Markers, start: int, end: int) -> bool:
    index = bisect_left(markers.starts, start)
    return index < len(markers.starts) and markers.ends[index] <= end


def _plain(text: str) -> str:
    return html.unescape(plain_markup(text))


def _compact(text: str) -> str:
    parts = [part for part in _COMPACT_PARTS.split(_plain(text)) if part]
    compact = "".join(
        part
        for index, part in enumerate(parts)
        if not (
            part.isspace()
            and (
                (index > 0 and parts[index - 1] in _COMPACT_PUNCTUATION)
                or (index + 1 < len(parts) and parts[index + 1] in _COMPACT_PUNCTUATION)
            )
        )
    ).strip()
    return _WORD_HYPHEN_SPACE.sub("-", _FLAG_START_SPACE.sub("--", compact))


def _literal_shape(literal: str) -> str | None:
    if _FILE_SUFFIX.search(literal) or "://" in literal or "/" in literal:
        return None
    if flag := _FLAG.match(literal):
        return flag.group()
    if (
        _QUALIFIED.fullmatch(literal.removesuffix("()"))
        or _CALL.fullmatch(literal)
        or _SNAKE.fullmatch(literal)
        or _ERROR_TYPE.fullmatch(literal)
    ):
        return literal.removesuffix("()")
    return None


def _technical_literals(target: str) -> tuple[str, ...]:
    prose, fragments = target_code_fragments(target)
    boundaries = tuple(row.start() for row in re.finditer(r"[.!?\n]", prose))
    authored = _markers(_AUTHORED_CONTEXT, prose)
    delivery = _markers(_DELIVERY_CONTEXT, prose)
    normalized: dict[str, str] = {}
    shapes: dict[str, str | None] = {}
    literals: dict[str, None] = {}
    for fragment in fragments:
        before = bisect_left(boundaries, fragment.start) - 1
        after = bisect_left(boundaries, fragment.end)
        prefix_start = boundaries[before] + 1 if before >= 0 else 0
        suffix_end = boundaries[after] if after < len(boundaries) else len(prose)
        if _contains_marker(authored, prefix_start, fragment.start) or _contains_marker(
            authored, fragment.end, suffix_end
        ):
            continue
        # Yalnız biçim çözümlemesini paylaş; aynı adın farklı bağlamları ayrı değerlendirilir.
        if fragment.text not in normalized:
            normalized[fragment.text] = _compact(fragment.text)
        literal = normalized[fragment.text]
        if _contains_marker(delivery, prefix_start, fragment.start) and not literal.endswith("()"):
            continue
        if literal not in shapes:
            shapes[literal] = _literal_shape(literal)
        if (candidate := shapes[literal]) is not None:
            literals[candidate] = None
    return tuple(literals)


def _has_literal(literal: str, source: str, *, unqualified: bool = False) -> bool:
    before = r"(?<![\w.:])" if unqualified else r"(?<!\w)"
    if literal.startswith("--"):
        before = r"(?<![\w-])"
    after = r"(?![\w-])" if literal.startswith("--") else r"(?!\w)"
    if re.search(before + re.escape(literal) + after, source):
        return True
    if _ERROR_TYPE.fullmatch(literal):
        # HTML okuması CamelCase adını sözcüklere ayırabilir; Warning ile Error ayrıdır.
        words = _CAMEL_WORD.findall(literal)
        return bool(
            re.search(before + r"\s*".join(map(re.escape, words)) + r"(?!\w)", source, re.I)
        )
    return False


def _has_necessary_name(literal: str, source: str, aliases: Mapping[str, str]) -> bool:
    if _has_literal(literal, source):
        return True
    if _QUALIFIED.fullmatch(literal):
        # Açık, niteliksiz taban adını kabul et; başka namespace altındaki aynı adı ödünç alma.
        # Nitelik/bileşen ilişkisi ve davranış yine anlamsal hakemin sorumluluğudur.
        basename = re.split(r"\.|::", literal)[-1]
        if _has_literal(basename, source, unqualified=True):
            return True
        head, separator, rest = literal.partition(".")
        if separator and head in aliases:
            return _has_literal(aliases[head] + "." + rest, source)
    return False


def _explicit_aliases(source: str) -> dict[str, str]:
    bindings: dict[str, set[str]] = {}
    declared: dict[str, set[int]] = {}
    for match in _IMPORT_ALIAS.finditer(source):
        bindings.setdefault(match["alias"], set()).add(_compact(match["module"]))
        declared.setdefault(match["alias"], set()).add(match.start("alias"))
    all_bindings: dict[str, set[int]] = {}
    for match in _AS_BINDING.finditer(source):
        all_bindings.setdefault(match["alias"], set()).add(match.start("alias"))
    assigned = {match["name"] for match in _ASSIGNMENT.finditer(source)}
    return {
        alias: next(iter(names))
        for alias, names in bindings.items()
        if len(names) == 1 and alias not in assigned and declared[alias] == all_bindings.get(alias)
    }


def unbacked_technical_literals(target: str, cited_sources: Iterable[str]) -> tuple[str, ...]:
    """Yalnız bu bulgunun atıf parçalarında tanınan adın gerekli metinsel desteğini ara."""
    literals = _technical_literals(target)
    if not literals:
        return ()
    # Alias yalnız aynı bulgunun atıf metnindeki açık, tek anlamlı import-as bildirimidir.
    cited = tuple(cited_sources)
    aliases = _explicit_aliases("\n".join(_plain(text) for text in cited))
    source = "\n".join(_compact(text) for text in cited)
    return tuple(
        literal for literal in literals if not _has_necessary_name(literal, source, aliases)
    )


_MISSING_PREVIEW_COUNT = 8
_NAME_PREVIEW_CHARS = 80
_MISSING_PREFIX = "Gösterilen kaynak bölümlerinde şu teknik adların metinsel desteği yok: "
_MISSING_SUFFIX = (
    ". İlgili API/uyarı/komut ayrıntısını içeren izinli kaynağı oku veya "
    "desteksiz ayrıntıyı düzelt. "
    "Bir adın geçmesi davranış veya kaldırılma kanıtı değildir."
)


def technical_support_basis(missing: tuple[str, ...], limit: int) -> str:
    """Bulgu kalır; yalnız ad önizlemesi kısalır ve gerçek atlanan ad sayısı gösterilir."""
    visible: list[str] = []
    for name in missing[:_MISSING_PREVIEW_COUNT]:
        preview = (
            name if len(name) <= _NAME_PREVIEW_CHARS else name[: _NAME_PREVIEW_CHARS - 1] + "…"
        )
        omitted = len(missing) - len(visible) - 1
        tail = f" (+{omitted} ad daha)" if omitted else ""
        candidate = _MISSING_PREFIX + ", ".join((*visible, preview)) + tail + _MISSING_SUFFIX
        if len(candidate) > limit:
            break
        visible.append(preview)
    if not visible:
        raise ValueError("Teknik bulgu önizlemesi verilen sınıra sığmadı.")
    omitted = len(missing) - len(visible)
    tail = f" (+{omitted} ad daha)" if omitted else ""
    return _MISSING_PREFIX + ", ".join(visible) + tail + _MISSING_SUFFIX

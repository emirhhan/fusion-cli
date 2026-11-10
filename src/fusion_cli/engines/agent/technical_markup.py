"""Teknik kanıt için tekrarlı son-ek taraması yapmayan dar işaretleme okuyucusu."""

from __future__ import annotations

import re
from bisect import bisect_right
from typing import NamedTuple

_TAG_START = re.compile(r"</?([A-Za-z][A-Za-z0-9:-]*)\b")
_FENCE_START = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n")
_MARKDOWN_CODE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
_OPAQUE_TAGS = frozenset({"script", "style", "pre"})


class CodeFragment(NamedTuple):
    start: int
    end: int
    text: str


class _Tag(NamedTuple):
    start: int
    end: int
    name: str
    closing: bool


def _tag_end(text: str, start: int) -> int | None:
    quote = ""
    for position in range(start, len(text)):
        char = text[position]
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == ">":
            return position + 1
    return None


def _tags(text: str) -> list[_Tag]:
    tags: list[_Tag] = []
    cursor = 0
    while (start := text.find("<", cursor)) >= 0:
        if text.startswith("<!--", start):
            comment_end = text.find("-->", start + 4)
            if comment_end < 0:
                break
            tags.append(_Tag(start, comment_end + 3, "comment", False))
            cursor = comment_end + 3
            continue
        match = _TAG_START.match(text, start)
        if match is None:
            cursor = start + 1
            continue
        end = _tag_end(text, match.end())
        if end is None:
            break  # Sonu olmayan etiketin kalanı atılmaz; düz metin olarak korunur.
        tags.append(_Tag(start, end, match[1].casefold(), text.startswith("</", start)))
        cursor = end
    return tags


def plain_markup(text: str) -> str:
    chunks: list[str] = []
    cursor = 0
    for tag in _tags(text):
        chunks.extend((text[cursor : tag.start], " "))
        cursor = tag.end
    chunks.append(text[cursor:])
    return "".join(chunks)


def _next_closing(tags: list[_Tag]) -> dict[int, int]:
    next_by_name: dict[str, int] = {}
    pairs: dict[int, int] = {}
    for index in range(len(tags) - 1, -1, -1):
        tag = tags[index]
        if tag.closing:
            next_by_name[tag.name] = index
        elif tag.name in next_by_name:
            pairs[index] = next_by_name[tag.name]
    return pairs


def _html_prose(text: str) -> tuple[str, list[CodeFragment]]:
    tags = _tags(text)
    closing = _next_closing(tags)
    chunks: list[str] = []
    fragments: list[CodeFragment] = []
    cursor = index = length = 0
    while index < len(tags):
        tag = tags[index]
        prefix = text[cursor : tag.start]
        chunks.append(prefix)
        length += len(prefix)
        pair = closing.get(index)
        if not tag.closing and pair is not None and tag.name in _OPAQUE_TAGS | {"code"}:
            end = tags[pair]
            if tag.name == "code":
                body = plain_markup(text[tag.end : end.start])
                rendered = "<code>" + body + "</code>"
                fragments.append(CodeFragment(length, length + len(rendered), body))
                chunks.append(rendered)
                length += len(rendered)
            else:
                chunks.append(" ")
                length += 1
            cursor, index = end.end, pair + 1
            continue
        chunks.append(" ")
        length += 1
        cursor, index = tag.end, index + 1
    chunks.append(text[cursor:])
    return "".join(chunks), fragments


def _without_fences(text: str) -> str:
    chunks: list[str] = []
    fence = ""
    for line in text.splitlines(keepends=True):
        if fence:
            closes = line.lstrip(" \t").startswith(fence)
            chunks.append(" " * len(line.rstrip("\n")) + ("\n" if line.endswith("\n") else ""))
            if closes:
                fence = ""
        elif match := _FENCE_START.match(line):
            fence = match[1]
            chunks.append(" " * len(line.rstrip("\n")) + "\n")
        else:
            chunks.append(line)
    return "".join(chunks)


def target_code_fragments(text: str) -> tuple[str, tuple[CodeFragment, ...]]:
    """Kod aralıklarını bir kez bul; kapatılmamış etiketlerde kalan iddiayı düşürme."""
    prose, html_fragments = _html_prose(text)
    prose = _without_fences(prose)
    html_fragments = [row for row in html_fragments if prose[row.start : row.end].strip()]
    starts = [row.start for row in html_fragments]
    fragments = list(html_fragments)
    for match in _MARKDOWN_CODE.finditer(prose):
        index = bisect_right(starts, match.start()) - 1
        if index >= 0 and match.start() < html_fragments[index].end:
            continue
        fragments.append(CodeFragment(match.start(), match.end(), match[1]))
    return prose, tuple(sorted(fragments, key=lambda row: row.start))


_LEGACY_OPAQUE_START = re.compile(r"<(style|script)\b", re.I)
_LEGACY_OPAQUE_END = {
    name: re.compile(r"</" + name + r"\s*>", re.I) for name in ("style", "script")
}


def _generic_tag_ends(text: str) -> list[int | None]:
    """Her konumdaki eski tırnaklı etiket alternatifinin bitişini bir kez hesapla."""
    ends: list[int | None] = [None] * (len(text) + 1)
    quotes: dict[str, int] = {}
    for position in range(len(text) - 1, -1, -1):
        char = text[position]
        if char == ">":
            ends[position] = position + 1
        elif char in "\"'":
            following = quotes.get(char)
            ends[position] = ends[following + 1] if following is not None else None
            quotes[char] = position
        else:
            ends[position] = ends[position + 1]
    return ends


def non_prose_text(text: str, *, preserve_offsets: bool = False) -> str:
    """Eski yorum/script/style/etiket alternasyonunu aynı öncelik ve boşluklarla uygula."""
    ends = _generic_tag_ends(text)
    greater = [row.start() for row in re.finditer(">", text)]
    comments = [row.end() for row in re.finditer("-->", text)]
    closings = {name: tuple(pattern.finditer(text)) for name, pattern in _LEGACY_OPAQUE_END.items()}
    closing_starts = {name: tuple(row.start() for row in rows) for name, rows in closings.items()}
    chunks: list[str] = []
    copied = cursor = 0
    while (start := text.find("<", cursor)) >= 0:
        end = None
        if text.startswith("<!--", start):
            index = bisect_right(comments, start + 6)
            if index < len(comments):
                end = comments[index]
        if end is None and (opening := _LEGACY_OPAQUE_START.match(text, start)) is not None:
            index = bisect_right(greater, opening.end() - 1)
            if index < len(greater):
                name = opening[1].casefold()
                following = bisect_right(closing_starts[name], greater[index])
                if following < len(closings[name]):
                    end = closings[name][following].end()
        if end is None:
            end = ends[start + 1]
        if end is None:
            cursor = start + 1
            continue
        chunks.extend((text[copied:start], " " * (end - start) if preserve_offsets else " "))
        copied = cursor = end
    chunks.append(text[copied:])
    return "".join(chunks)

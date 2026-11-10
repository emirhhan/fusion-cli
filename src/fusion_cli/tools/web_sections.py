"""Bounded, conservative exact-id HTML subtree selection (no persistent store)."""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape
from html.parser import HTMLParser

MAX_SECTION_ID_CHARS = 512
MAX_SECTION_DEPTH = 128
MAX_PENDING_MARKUP_CHARS = 65_536
_VOID = frozenset(
    [
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ]
)
_HIDDEN = frozenset({"script", "style", "noscript"})
_TAG_NAME = re.compile(r"<[a-zA-Z][\w:.-]*")
_END_TAG = re.compile(r"</[a-zA-Z][\w:.-]*\s*>")


class SectionError(ValueError):
    """The response cannot prove one complete, well-formed selected subtree."""


def _valid_start(raw: str) -> bool:
    """Linear lexical validation; HTMLParser deliberately tolerates broken attributes."""
    match = _TAG_NAME.match(raw)
    if match is None:
        return False
    i = match.end()
    while i < len(raw):
        before = i
        while i < len(raw) and raw[i].isspace():
            i += 1
        if (i == len(raw) - 1 and raw[i] == ">") or (i == len(raw) - 2 and raw.startswith("/>", i)):
            return True
        if i == before:
            return False
        start = i
        while i < len(raw) and not raw[i].isspace() and raw[i] not in "/=>\"'<`":
            i += 1
        if i == start:
            return False
        attribute_end = i
        while i < len(raw) and raw[i].isspace():
            i += 1
        if i < len(raw) and raw[i] == "=":
            i += 1
            while i < len(raw) and raw[i].isspace():
                i += 1
            if i >= len(raw):
                return False
            if raw[i] in "\"'":
                end = raw.find(raw[i], i + 1)
                if end < 0:
                    return False
                i = end + 1
            else:
                start = i
                while i < len(raw) and not raw[i].isspace() and raw[i] not in ">\"'=<>`":
                    i += 1
                if i == start:
                    return False
        else:
            i = attribute_end
    return False


class _VisibleText(HTMLParser):
    """Access-wall probe: retain at most the visible prefix inspected by the wall gate."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden: list[str] = []
        self.parts: list[str] = []
        self.size = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HIDDEN:
            if len(self.hidden) >= MAX_SECTION_DEPTH:
                raise SectionError("Hidden markup nesting limit exceeded.")
            self.hidden.append(tag)
        self.handle_data(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _VOID:
            raise SectionError("Self-closing nonvoid HTML element.")
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN:
            if not self.hidden or self.hidden[-1] != tag:
                raise SectionError("Mismatched hidden closing tag.")
            self.hidden.pop()
        self.handle_data(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden and self.size < 4000:
            normalized = re.sub(r"\s+", " ", data)
            if not self.parts or self.parts[-1].endswith(" "):
                normalized = normalized.lstrip(" ")
            part = normalized[: 4000 - self.size]
            if not part:
                return
            self.parts.append(part)
            self.size += len(part)


def access_wall_text(body: str, *, cancelled: Callable[[], bool]) -> str:
    parser = _VisibleText()
    for start in range(0, len(body), 16_384):
        if cancelled():
            raise SectionError("Section read cancelled.")
        parser.feed(body[start : start + 16_384])
        if len(parser.rawdata) > MAX_PENDING_MARKUP_CHARS:
            raise SectionError("HTML token buffering limit exceeded.")
        if parser.size >= 4000:
            break
    return "".join(parser.parts)


class _SectionParser(HTMLParser):
    def __init__(self, body: str, section_id: str) -> None:
        super().__init__(convert_charrefs=False)
        self.body = body
        self.line = 1
        self.line_offset = 0
        self.section_id = section_id
        self.matches = 0
        self.stack: list[str] = []
        self.parts: list[str] = []
        self.depth = 0
        self.hidden: list[str] = []

    def _offset(self) -> int:
        line, column = self.getpos()
        while self.line < line:
            self.line_offset = self.body.index("\n", self.line_offset) + 1
            self.line += 1
        return self.line_offset + column

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], closed: bool) -> None:
        if tag in _HIDDEN and not closed:
            if len(self.hidden) >= MAX_SECTION_DEPTH:
                raise SectionError("Hidden markup nesting limit exceeded.")
            self.hidden.append(tag)
        ids = [value for name, value in attrs if name == "id"]
        selected = self.section_id in ids
        if selected:
            self.matches += 1
            if self.matches != 1 or len(ids) != 1:
                raise SectionError("Duplicate section id.")
        if self.stack or selected:
            raw = self.get_starttag_text()
            if raw is None or not _valid_start(raw):
                raise SectionError("Malformed selected markup.")
            if tag not in _HIDDEN and not self.hidden:
                # Normalize attributes so hidden markup-like attribute values never enter
                # the legacy regex renderer. Only actual anchor destinations are evidence.
                href = dict(attrs).get("href") if tag == "a" else None
                attribute = f' href="{escape(href, quote=True)}"' if href else ""
                self.parts.append(f"<{tag}{attribute}>")
            if not closed and tag not in _VOID:
                if len(self.stack) >= MAX_SECTION_DEPTH:
                    raise SectionError("Selected markup nesting limit exceeded.")
                self.stack.append(tag)
        if not closed and tag not in _VOID:
            self.depth += 1
            if self.depth > MAX_SECTION_DEPTH:
                raise SectionError("HTML nesting limit exceeded.")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _VOID:
            raise SectionError("Self-closing nonvoid HTML element.")
        self._start(tag, attrs, True)

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN and (not self.hidden or self.hidden[-1] != tag):
            raise SectionError("Mismatched hidden closing tag.")
        if self.stack:
            offset = self._offset()
            end = self.body.find(">", offset)
            if tag != self.stack[-1] or _END_TAG.fullmatch(self.body[offset : end + 1]) is None:
                raise SectionError("Malformed selected nesting.")
            if not self.hidden:
                self.parts.append(f"</{tag}>")
            self.stack.pop()
        if tag in _HIDDEN:
            self.hidden.pop()
        if tag not in _VOID:
            self.depth = max(0, self.depth - 1)

    def handle_data(self, data: str) -> None:
        if self.stack and not self.hidden:
            if "<" in data:
                raise SectionError("Malformed selected text markup.")
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")

    def handle_decl(self, decl: str) -> None:
        if self.stack:
            raise SectionError("Declaration inside selected markup.")

    def unknown_decl(self, data: str) -> None:
        if self.stack:
            raise SectionError("Unknown declaration in selected markup.")


def select_section(body: str, section_id: str, *, cancelled: Callable[[], bool]) -> str:
    """Scan the entire capped response; count only the requested decoded id."""
    parser = _SectionParser(body, section_id)
    for start in range(0, len(body), 16_384):
        if cancelled():
            raise SectionError("Section read cancelled.")
        parser.feed(body[start : start + 16_384])
        if len(parser.rawdata) > MAX_PENDING_MARKUP_CHARS:
            raise SectionError("HTML token buffering limit exceeded.")
    parser.close()
    if cancelled():
        raise SectionError("Section read cancelled.")
    if parser.matches != 1 or parser.stack or parser.hidden:
        raise SectionError("Section missing or unclosed.")
    return "".join(parser.parts)

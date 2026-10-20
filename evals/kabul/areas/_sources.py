"""Ajanın yazdığı web kaynaklarını (html/css/js) toplayan saf yardımcılar."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

#: Taranmayacak klasör adı (bağımlılık deposu); nokta ile başlayanlar da atlanır.
SKIPPED_DIRECTORY = "node_modules"
#: Tek dosya için okuma tavanı (bayt); dev paketlenmiş kütüphaneler ölçümü şişirmesin.
MAX_FILE_BYTES = 2_000_000

_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
_SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
_STYLE_ATTRIBUTE = re.compile(r"""\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_HTML_SUFFIXES = frozenset({".html", ".htm"})
_SCRIPT_SUFFIXES = frozenset({".js", ".mjs"})
_STYLE_SUFFIXES = frozenset({".css"})


@dataclass(frozen=True, slots=True)
class Sources:
    """Klasördeki kaynakların türüne göre birleştirilmiş metni."""

    html: str = ""
    css: str = ""
    js: str = ""

    @property
    def everything(self) -> str:
        return "\n".join((self.html, self.css, self.js))


def iter_files(root: Path, suffixes: frozenset[str]) -> Iterator[Path]:
    """Verilen uzantılı dosyaları sıralı gez; `node_modules` ve gizli klasörleri atla."""
    stack = [root]
    while stack:
        directory = stack.pop()
        for entry in sorted(directory.iterdir()):
            if entry.name.startswith(".") or entry.name == SKIPPED_DIRECTORY:
                continue
            if entry.is_dir():
                stack.append(entry)
            elif entry.suffix.lower() in suffixes:
                yield entry


def _read(path: Path) -> str:
    if path.stat().st_size > MAX_FILE_BYTES:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _inline_styles(html: str) -> list[str]:
    """`style="..."` özniteliklerini `x{...}` kuralına sararak CSS gibi okunur yap."""
    wrapped = [f"x{{{double or single}}}" for double, single in _STYLE_ATTRIBUTE.findall(html)]
    return [*_STYLE_BLOCK.findall(html), *wrapped]


def collect_sources(root: Path) -> Sources:
    """Klasördeki html/css/js dosyalarını (satır içi `<style>`/`<script>` dahil) topla."""
    html_parts: list[str] = []
    css_parts: list[str] = []
    js_parts: list[str] = []
    suffixes = _HTML_SUFFIXES | _SCRIPT_SUFFIXES | _STYLE_SUFFIXES
    for path in iter_files(root, suffixes):
        text = _read(path)
        suffix = path.suffix.lower()
        if suffix in _HTML_SUFFIXES:
            html_parts.append(text)
            css_parts.extend(_inline_styles(text))
            js_parts.extend(_SCRIPT_BLOCK.findall(text))
        elif suffix in _STYLE_SUFFIXES:
            css_parts.append(text)
        else:
            js_parts.append(text)
    return Sources("\n".join(html_parts), "\n".join(css_parts), "\n".join(js_parts))

"""Keşif araçları: metin/regex arama ve dosya deseni.

İkisi de gürültü dizinlerini atlar ve üst sınırla çalışır: modelin bağlamına
binlerce satır boca etmek sinyali gürültüde boğar.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..core.constants import (
    MAX_GLOB_MATCHES,
    MAX_MATCH_LINE_CHARS,
    MAX_SEARCH_HITS,
    MAX_SEARCHABLE_FILE_BYTES,
    SKIP_DIRECTORIES,
)
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import optional_str, require_str
from .files import display_path, resolve_path


def search_code(args: ToolArgs, context: ToolContext) -> ToolResult:
    pattern = require_str(args, "pattern")
    root = resolve_path(context, optional_str(args, "path", "."))

    if not root.exists():
        return ToolResult.failure(f"Yol yok: {root}")
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return ToolResult.failure(f"Geçersiz regex: {exc}")

    hits: list[str] = []
    for path in _searchable_files(root):
        for number, line in _matching_lines(path, regex):
            hits.append(f"{path}:{number}: {line.strip()[:MAX_MATCH_LINE_CHARS]}")
            if len(hits) >= MAX_SEARCH_HITS:
                return ToolResult(
                    "\n".join(hits) + f"\n… ({MAX_SEARCH_HITS}+ eşleşme, deseni daraltın)"
                )
    return ToolResult("\n".join(hits) if hits else "(eşleşme yok)")


def glob_files(args: ToolArgs, context: ToolContext) -> ToolResult:
    pattern = require_str(args, "pattern")
    root = resolve_path(context, optional_str(args, "path", "."))

    if not root.exists():
        return ToolResult.failure(f"Yol yok: {root}")

    # MUTLAK desen `Path.glob`'da ham `NotImplementedError` fırlatır ve model
    # ekranda Python istisnası görür — ne olduğunu ne yapacağını anlamaz.
    # Ölçüldü: model `glob("/*")` çağırdı, araç çöktü ve tur "ilerleme yok" ile
    # öldü. Desen köke GÖRELİDİR; mutlak yol için `path` alanı vardır.
    if pattern.startswith("/") or (len(pattern) > 1 and pattern[1] == ":"):
        return ToolResult.failure(
            f"'{pattern}' mutlak bir yol. glob deseni arama köküne GÖRELİ olmalı "
            "(ör. '**/*.tsx'). Başka bir dizinde arayacaksan 'path' alanını kullan."
        )

    matches: list[str] = []
    try:
        aday = sorted(root.glob(pattern))
    except (NotImplementedError, ValueError) as error:
        return ToolResult.failure(
            f"Geçersiz glob deseni '{pattern}': {error}. Göreli bir desen dene, "
            "ör. '**/*.py' ya da 'src/**/*.ts'."
        )
    for path in aday:
        if not path.is_file() or _is_skipped(path):
            continue
        matches.append(display_path(context, path))
        if len(matches) >= MAX_GLOB_MATCHES:
            matches.append(f"… ({MAX_GLOB_MATCHES}+ dosya, deseni daraltın)")
            break
    return ToolResult("\n".join(matches) if matches else "(eşleşen dosya yok)")


# --------------------------------------------------------------------------- #


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRECTORIES for part in path.parts)


def _searchable_files(root: Path) -> Iterator[Path]:
    candidates = [root] if root.is_file() else root.rglob("*")
    for path in candidates:
        if not path.is_file() or _is_skipped(path):
            continue
        try:
            if path.stat().st_size > MAX_SEARCHABLE_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def _matching_lines(path: Path, regex: re.Pattern[str]) -> Iterator[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for number, line in enumerate(text.splitlines(), 1):
        if regex.search(line):
            yield number, line

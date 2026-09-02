"""Keşif araçları: metin/regex arama ve dosya deseni.

İkisi de gürültü dizinlerini atlar ve üst sınırla çalışır: modelin bağlamına
binlerce satır boca etmek sinyali gürültüde boğar.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..core.constants import (
    MAX_GLOB_MATCHES,
    MAX_MATCH_LINE_CHARS,
    MAX_SEARCH_HITS,
    MAX_SEARCHABLE_FILE_BYTES,
    SKIP_DIRECTORIES,
)
from ..core.redaction import redact
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import optional_str, require_str
from .files import display_path, resolve_path

SEARCH_DEADLINE_S = 8.0
MAX_SEARCH_CANDIDATES = 50_000


@dataclass
class _SearchScan:
    context: ToolContext
    started: float
    candidates: int = 0
    stopped: str | None = None

    def should_stop(self) -> bool:
        if self.context.cancelled.is_set():
            self.stopped = "kullanıcı tarafından iptal edildi"
        elif time.monotonic() - self.started >= SEARCH_DEADLINE_S:
            self.stopped = f"{SEARCH_DEADLINE_S:g}s süre sınırına ulaştı"
        elif self.candidates >= MAX_SEARCH_CANDIDATES:
            self.stopped = f"{MAX_SEARCH_CANDIDATES} dosyalık aday sınırına ulaştı"
        return self.stopped is not None


def _bounded_result(lines: list[str], scan: _SearchScan, empty: str) -> ToolResult:
    if scan.stopped is None:
        return ToolResult("\n".join(lines) if lines else empty)
    partial = "\n".join(lines) if lines else "(bu sınır içinde eşleşme bulunmadı)"
    return ToolResult.failure(
        f"{partial}\n\nArama {scan.stopped}; {scan.candidates} dosya adayı incelendi. "
        "Bu sonuç kısmidir ve tekrar denenebilir: aynı geniş aramayı yinelemek yerine "
        "'path' alanını Desktop, Documents veya belirli bir proje klasörüyle daraltın."
    )


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
    scan = _SearchScan(context=context, started=time.monotonic())
    for path in _searchable_files(root, scan):
        for number, line in _matching_lines(path, regex):
            hits.append(
                f"{display_path(context, path)}:{number}: "
                f"{redact(line.strip())[:MAX_MATCH_LINE_CHARS]}"
            )
            if len(hits) >= MAX_SEARCH_HITS:
                return ToolResult(
                    "\n".join(hits) + f"\n… ({MAX_SEARCH_HITS}+ eşleşme, deseni daraltın)"
                )
    return _bounded_result(hits, scan, "(eşleşme yok)")


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
    scan = _SearchScan(context=context, started=time.monotonic())
    for path in _searchable_files(root, scan):
        relative = path.relative_to(root) if root.is_dir() else Path(path.name)
        matched = relative.match(pattern)
        if not matched and pattern.startswith("**/"):
            matched = relative.match(pattern[3:])
        if not matched:
            continue
        matches.append(display_path(context, path))
        if len(matches) >= MAX_GLOB_MATCHES:
            matches.append(f"… ({MAX_GLOB_MATCHES}+ dosya, deseni daraltın)")
            break
    return _bounded_result(matches, scan, "(eşleşen dosya yok)")


# --------------------------------------------------------------------------- #


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRECTORIES for part in path.parts) or _is_secret_file(path)


def _is_secret_file(path: Path) -> bool:
    """Arama çıktısına dotenv ve açık sır dosyalarını hiç sokma."""
    name = path.name.casefold()
    return name == ".env" or name.startswith(".env.")


def _searchable_files(root: Path, scan: _SearchScan) -> Iterator[Path]:
    if root.is_file():
        candidates: Iterator[Path] = iter((root,))
    else:
        def walk() -> Iterator[Path]:
            for current, directories, files in os.walk(root, followlinks=False):
                directories[:] = sorted(
                    name for name in directories if name not in SKIP_DIRECTORIES
                )
                for name in sorted(files):
                    yield Path(current) / name

        candidates = walk()
    for path in candidates:
        if scan.should_stop():
            return
        scan.candidates += 1
        if _is_skipped(path):
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

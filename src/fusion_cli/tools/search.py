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
MAX_SEARCH_SCAN_BYTES = 256 * 1024
MAX_SEARCH_LINE_BYTES = 16 * 1024
MAX_REGEX_PATTERN_CHARS = 500
_UNSAFE_REGEX = re.compile(r"\([^()\n]{0,200}\)(?:[+*]|\{\d)")
_SECRET_FILE_NAMES = frozenset(
    {
        ".npmrc", ".netrc", ".git-credentials", ".pypirc", "credentials",
        "credentials.json", "credentials.yaml", "credentials.yml", "token.json",
        "tokens.json", "auth.json", "secrets.json", "secret.json", "config.json",
        "config.yaml", "config.yml", "id_rsa", "id_ed25519",
    }
)
_SECRET_DIRECTORY_NAMES = frozenset(
    {
        ".aws", ".azure", ".claude", "claude", ".config", ".gnupg", ".ssh", "chrome",
        "application support", "cache", "caches", "vendor",
    }
)
_SKIP_DIRECTORY_NAMES = frozenset(
    name.casefold() for name in (*SKIP_DIRECTORIES, *_SECRET_DIRECTORY_NAMES)
)


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
    root = resolve_path(context, optional_str(args, "path", ".")).resolve()

    if not root.exists():
        return ToolResult.failure(f"Yol yok: {root}")
    if len(pattern) > MAX_REGEX_PATTERN_CHARS or _UNSAFE_REGEX.search(pattern):
        return ToolResult.failure(
            "Regex deseni güvenli sınırı aşıyor veya patolojik geri izleme riski taşıyor; "
            "daha kısa ve basit bir desen dene."
        )
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return ToolResult.failure(f"Geçersiz regex: {exc}")

    hits: list[str] = []
    scan = _SearchScan(context=context, started=time.monotonic())
    for path in _searchable_files(root, scan):
        for number, line in _matching_lines(path, regex, scan):
            hits.append(
                f"{display_path(context, path)}:{number}: "
                f"{redact(line.strip())[:MAX_MATCH_LINE_CHARS]}"
            )
            if len(hits) >= MAX_SEARCH_HITS:
                return ToolResult.failure(
                    "\n".join(hits) + f"\n… ({MAX_SEARCH_HITS}+ eşleşme; sonuç kısmidir, "
                    "deseni daraltın)"
                )
    return _bounded_result(hits, scan, "(eşleşme yok)")


def glob_files(args: ToolArgs, context: ToolContext) -> ToolResult:
    pattern = require_str(args, "pattern")
    root = resolve_path(context, optional_str(args, "path", ".")).resolve()

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
    return (
        any(_is_skipped_directory_name(part) for part in path.parts)
        or _is_secret_file(path)
        or path.is_symlink()
    )


def _is_skipped_directory_name(name: str) -> bool:
    return name.casefold() in _SKIP_DIRECTORY_NAMES


def _is_secret_file(path: Path) -> bool:
    """Arama çıktısına dotenv ve açık sır dosyalarını hiç sokma."""
    name = path.name.casefold()
    return name == ".env" or name.startswith(".env.") or name in _SECRET_FILE_NAMES


def _searchable_files(root: Path, scan: _SearchScan) -> Iterator[Path]:
    if root.is_file():
        candidates: Iterator[Path] = iter((root,))
    else:
        def walk() -> Iterator[Path]:
            for current, directories, files in os.walk(root, followlinks=False):
                directories[:] = sorted(
                    name for name in directories if not _is_skipped_directory_name(name)
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


def _matching_lines(
    path: Path, regex: re.Pattern[str], scan: _SearchScan
) -> Iterator[tuple[int, str]]:
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_SEARCH_SCAN_BYTES + 1)
    except OSError:
        return
    if len(data) > MAX_SEARCH_SCAN_BYTES:
        scan.stopped = f"tek dosya {MAX_SEARCH_SCAN_BYTES} bayt okuma sınırına ulaştı"
    text = data[:MAX_SEARCH_SCAN_BYTES].decode("utf-8", errors="ignore")
    for number, line in enumerate(text.splitlines(), 1):
        if scan.should_stop():
            return
        if len(line.encode("utf-8")) > MAX_SEARCH_LINE_BYTES:
            scan.stopped = f"tek satır {MAX_SEARCH_LINE_BYTES} bayt eşleme sınırına ulaştı"
            line = line[:MAX_SEARCH_LINE_BYTES]
        if regex.search(line):
            yield number, line

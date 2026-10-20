"""Kök veya iki proje katmanı altındaki src ağacını güvenli sınırla bulur."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ._sources import MAX_FILE_BYTES, SKIPPED_DIRECTORY

# Kabul çıktısı root/fusion-tanitim/video/src olabilir; daha derin kök taranmaz.
MAX_PROJECT_DEPTH = 2
_SKIPPED = frozenset({SKIPPED_DIRECTORY, "private", "public", "out", "dist", "build"})
_SUFFIXES = frozenset({".ts", ".tsx"})


def _entries(directory: Path) -> Iterator[Path]:
    for entry in sorted(directory.iterdir()):
        if entry.is_symlink() or entry.name.startswith(".") or entry.name in _SKIPPED:
            continue
        yield entry


def _source_roots(root: Path) -> Iterator[Path]:
    stack = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        for entry in _entries(directory):
            if not entry.is_dir():
                continue
            if entry.name == "src":
                yield entry
            elif depth < MAX_PROJECT_DEPTH:
                stack.append((entry, depth + 1))


def remotion_sources(root: Path) -> Iterator[Path]:
    """Prepared TS örneklerini değil yalnız gerçek src dosyalarını döndür."""
    for folder in _source_roots(root):
        stack = [folder]
        while stack:
            for entry in _entries(stack.pop()):
                if entry.is_dir():
                    stack.append(entry)
                elif entry.suffix.lower() in _SUFFIXES and entry.stat().st_size <= MAX_FILE_BYTES:
                    yield entry

"""Kod değişikliğiyle görsel/belge teslimini aynı kapıya yönlendirme."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})
DOCUMENT_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx", ".pptx"})
MEDIA_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".mkv", ".mp3", ".wav", ".ogg"})
ARTIFACT_SUFFIXES = IMAGE_SUFFIXES | DOCUMENT_SUFFIXES | MEDIA_SUFFIXES


def artifact_only(paths: Iterable[str | Path]) -> bool:
    """En az bir değişiklik var ve bütün değişiklikler kod dışı teslim mi?"""
    suffixes = tuple(Path(path).suffix.lower() for path in paths)
    return bool(suffixes) and all(suffix in ARTIFACT_SUFFIXES for suffix in suffixes)

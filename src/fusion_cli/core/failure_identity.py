"""Kontrol kimliklerini ham serbest metin taşımadan kararlı biçimde koru."""

from __future__ import annotations

import hashlib
import re

_IDENTIFIER = re.compile(r"[a-zA-Z0-9_.:/-]+\Z")


def is_safe_failure_identity(value: str) -> bool:
    """Kısa protokol kimliği ham yol, sorgu veya serbest açıklama değildir."""
    return (
        bool(_IDENTIFIER.fullmatch(value))
        and not value.startswith("/")
        and not any(
            part in {"..", "."} or part.lower().startswith(".env") for part in value.split("/")
        )
    )


def failure_identity(value: str) -> str:
    """Serbest Unicode/açıklama için kararlı opak SHA-256 kimliği üret."""
    if not value.strip():
        raise ValueError("Kontrol kimliği boş olamaz.")
    if is_safe_failure_identity(value):
        return value
    return "opaque:" + hashlib.sha256(value.encode("utf-8")).hexdigest()

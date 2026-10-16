"""Aynı dizinde benzersiz temp ve replace ile kalıcı dosya transaction'ı."""

from __future__ import annotations

import errno
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AtomicWriteReceipt:
    directory_synced: bool


class AtomicCommitUncertainError(OSError):
    """Replace gerçekleşti; directory fsync kanıtı yok. Kör tekrar yapılmaz."""

    committed = True


def atomic_replace_text(target: Path, text: str) -> AtomicWriteReceipt:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
        return AtomicWriteReceipt(directory_synced=_sync_directory(target.parent))
    finally:
        temporary.unlink(missing_ok=True)


def atomic_create_bytes(target: Path, data: bytes) -> AtomicWriteReceipt:
    """Tam yazılmış baytları yayımla; mevcut hedefin üstüne asla yazma."""
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
        return AtomicWriteReceipt(directory_synced=_sync_directory(target.parent))
    finally:
        temporary.unlink(missing_ok=True)


def _sync_directory(directory: Path) -> bool:
    if os.name == "nt":
        return False
    descriptor: int | None = None
    try:
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.fsync(descriptor)
        return True
    except OSError as error:
        if error.errno in {errno.EINVAL, errno.ENOTSUP}:
            return False
        raise AtomicCommitUncertainError(
            "Dosya değiştirildi; kalıcı directory kaydı doğrulanamadı."
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)

"""Her bileşeni no-follow açarak köke bağlı, kararlı kaynak baytlarını oku."""

from __future__ import annotations

import os
import stat
from contextlib import ExitStack
from pathlib import Path


def read_scoped_source(root: Path, relative: Path, *, max_bytes: int) -> bytes | None:
    """Politika uygulama; sınır/tür/kararlılık doğrulanamıyorsa bayt döndürme.

    Kök mutlak, kaynak yolu göreli ve ikisi de traversal içermeyen yollar olmalı.
    Her bileşen descriptor'a bağlanır; desteklenmeyen platformda açık okuma yoktur.
    Kaynak uzantısı, gizli dosya ve izin politikası çağıranın sorumluluğundadır.
    """
    if (
        not root.is_absolute()
        or relative.is_absolute()
        or not relative.parts
        or ".." in (*root.parts, *relative.parts)
        or type(max_bytes) is not int
        or max_bytes < 0
    ):
        return None
    if (
        os.name != "posix"
        or os.open not in os.supports_dir_fd
        or not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"))
    ):
        return None
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        components = (*root.relative_to(root.anchor).parts, *relative.parts)
        with ExitStack() as cleanup:
            parent = os.open(root.anchor, directory_flags)
            cleanup.callback(os.close, parent)
            for component in components[:-1]:
                parent = os.open(component, directory_flags, dir_fd=parent)
                cleanup.callback(os.close, parent)
            descriptor = os.open(
                components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
            cleanup.callback(os.close, descriptor)
            return _read_descriptor(descriptor, max_bytes)
    except (OSError, ValueError, NotImplementedError):
        return None


def _read_descriptor(descriptor: int, max_bytes: int) -> bytes | None:
    """Düzenli dosyayı aynı descriptor'dan en çok tavan+1 bayt okuyup yeniden doğrula."""
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
        return None
    payload = bytearray()
    while len(payload) <= max_bytes:
        block = os.read(descriptor, max_bytes + 1 - len(payload))
        if not block:
            break
        payload.extend(block)
    if len(payload) > max_bytes:
        return None
    after = os.fstat(descriptor)
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or len(payload) != after.st_size
    ):
        return None
    return bytes(payload)

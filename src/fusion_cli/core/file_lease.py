"""Sırlar taşımayan, süreç ömrüne bağlı advisory dosya kilidi."""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path


class FileLease:
    """Aynı dosyada ayrı süreç ve thread'lerin transaction'larını ayırır."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._descriptor: int | None = None

    def try_acquire(self) -> bool:
        """Beklemeden dene; dosya kalır, kilit FD kapanınca OS tarafından bırakılır."""
        if self._descriptor is not None:
            return True
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(
            self._path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        try:
            if sys.platform == "win32":
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(descriptor)
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                return False
            raise
        self._descriptor = descriptor
        return True

    def close(self) -> None:
        """Kilidi bırak; inode silinmez, başka süreç için ikinci kilit oluşmaz."""
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None

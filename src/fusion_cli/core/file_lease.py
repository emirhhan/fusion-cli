"""Sırlar taşımayan, süreç ömrüne bağlı advisory dosya kilidi."""

from __future__ import annotations

import errno
import os
import stat
import sys
from pathlib import Path


class FileLease:
    """Aynı dosyada ayrı süreç ve thread'lerin transaction'larını ayırır."""

    def __init__(self, path: Path, *, dir_fd: int | None = None) -> None:
        if dir_fd is not None and (
            path.is_absolute() or len(path.parts) != 1 or path.name in {".", ".."}
        ):
            raise ValueError("Dizin tanıtıcılı kilit tek bir göreli dosya adı ister.")
        self._path = path
        self._dir_fd = dir_fd
        self._descriptor: int | None = None

    def try_acquire(self) -> bool:
        """Beklemeden dene; dosya kalır, kilit FD kapanınca OS tarafından bırakılır."""
        if self._descriptor is not None:
            return True
        descriptor = self._open()
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

    def _open(self) -> int:
        if self._dir_fd is None:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            return os.open(self._path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise OSError("Güvenli dizin tanıtıcılı kilit bu platformda yok.")
        descriptor = os.open(
            self._path,
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=self._dir_fd,
        )
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
        ):
            os.close(descriptor)
            raise OSError("Kilit dosyasının türü, sahibi veya izinleri uygun değil.")
        return descriptor

    def close(self) -> None:
        """Kilidi bırak; inode silinmez, başka süreç için ikinci kilit oluşmaz."""
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None

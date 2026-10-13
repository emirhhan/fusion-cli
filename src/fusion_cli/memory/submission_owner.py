"""Süreç PID'sinden bağımsız, kilit ömrüyle kanıtlanan yürütme sahibi."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import BinaryIO


class SubmissionOwner:
    """Her adaptör nesnesi kendi epoch kilidini kapatana kadar sahip kalır."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._handle: BinaryIO | None = None
        self._epoch: str | None = None

    @staticmethod
    def _lock(handle: BinaryIO) -> None:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def epoch(self) -> str:
        """Kabul transaction'ından önce benzersiz kilit generation'ını açar."""
        if self._epoch is None:
            self._directory.mkdir(parents=True, exist_ok=True)
            descriptor, filename = tempfile.mkstemp(prefix="owner-", dir=self._directory)
            self._handle = os.fdopen(descriptor, "r+b")
            self._handle.write(b"0")
            self._handle.flush()
            self._lock(self._handle)
            self._epoch = Path(filename).name
        return self._epoch

    def is_alive(self, epoch: str) -> bool:
        """PID yeniden kullanılsa da eski generation canlı kabul edilmez."""
        if epoch == self._epoch and self._handle is not None:
            return True
        if Path(epoch).name != epoch:
            return False
        try:
            with (self._directory / epoch).open("r+b") as handle:
                try:
                    self._lock(handle)
                except OSError:
                    return True
                return False
        except FileNotFoundError:
            return False

    def close(self) -> None:
        """Kilit bırakılır; kalan unfinished metadata artık observation ister."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        if self._epoch is not None:
            (self._directory / self._epoch).unlink(missing_ok=True)

"""Explicit cooperative physical-read budget shared by one optional projection."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Iterator
from pathlib import Path

READ_BYTES = 32 * 1024 * 1024
READ_ENTRIES = 20_000
READ_CHUNK = 65_536


class ReadBudgetExceededError(RuntimeError):
    """Incomplete optional input must never become a complete digest or evidence."""


class ReadBudget:
    def __init__(
        self,
        *,
        max_bytes: int = READ_BYTES,
        max_entries: int = READ_ENTRIES,
        valid: Callable[[], bool] = lambda: True,
    ) -> None:
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.bytes_read = 0
        self.entries_read = 0
        self._valid = valid
        self.exhausted = False

    def fail(self) -> None:
        self.exhausted = True
        raise ReadBudgetExceededError("Optional read budget unavailable.")

    def check(self) -> None:
        if self.exhausted or not self._valid():
            self.fail()

    def entry(self) -> None:
        self.check()
        if self.entries_read >= self.max_entries:
            self.fail()
        self.entries_read += 1

    def iterdir(self, path: Path) -> Iterator[os.DirEntry[str]]:
        self.check()
        with os.scandir(path) as entries:
            while True:
                self.check()
                if self.entries_read >= self.max_entries:
                    self.fail()
                try:
                    entry = next(entries)
                except StopIteration:
                    return
                self.entry()
                yield entry

    def chunks(self, path: Path) -> Iterator[bytes]:
        """Only regular files; no oversized pre-read, partial success or EOF over-read."""
        self.entry()
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise OSError("Optional input is not a regular file.")
            if before.st_size > self.max_bytes - self.bytes_read:
                self.fail()
            remaining = before.st_size
            while remaining:
                self.check()
                chunk = os.read(
                    descriptor, min(READ_CHUNK, remaining, self.max_bytes - self.bytes_read)
                )
                self.bytes_read += len(chunk)
                if not chunk:
                    self.fail()
                remaining -= len(chunk)
                yield chunk
            self.check()
            after = os.fstat(descriptor)
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ino,
            ):
                self.fail()
        finally:
            os.close(descriptor)

    def read_bytes(self, path: Path) -> bytes:
        return b"".join(self.chunks(path))

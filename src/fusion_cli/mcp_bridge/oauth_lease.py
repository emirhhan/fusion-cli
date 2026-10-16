"""OAuth transaction'ı için loop kilidi ve isteğe bağlı süreçler arası lease."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import TracebackType
from typing import Protocol

from ..core.constants import FILE_LOCK_POLL_S
from ..core.file_lease import FileLease
from ..core.owned_thread import await_owned_thread


class AsyncLease(Protocol):
    async def __aenter__(self) -> None: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def locked(self) -> bool: ...


class OAuthLease:
    """Yerel waiter iptali başka backend'in aktif transaction'ını bozmaz."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._file: FileLease | None = None

    def locked(self) -> bool:
        return self._lock.locked()

    async def __aenter__(self) -> None:
        await self._lock.acquire()
        try:
            if self._path is not None:
                self._file = FileLease(self._path)
                # OS dosya kilidi süreçler arasıdır; asyncio.Event bildirim kaynağı yoktur.
                while not await await_owned_thread(self._file.try_acquire):  # noqa: ASYNC110
                    await asyncio.sleep(FILE_LOCK_POLL_S)
        except BaseException:
            try:
                if self._file is not None:
                    await await_owned_thread(self._file.close)
            finally:
                self._file = None
                self._lock.release()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if self._file is not None:
                await await_owned_thread(self._file.close)
        finally:
            self._file = None
            self._lock.release()

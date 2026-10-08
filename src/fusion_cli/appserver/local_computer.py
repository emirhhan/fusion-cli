"""Salt okunur yerel bilgisayar sondası; host bağı model girdisinden üretilmez."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from ..core.tools import ToolArgs, ToolContext, ToolResult


@dataclass(frozen=True, slots=True)
class LocalHost:
    """Sahip olunan native sürecin değişmez kaynağı ve oturum kimliği."""

    source_id: str
    session_id: str
    platform: str

    def __post_init__(self) -> None:
        if not self.source_id or not self.session_id:
            raise ValueError("Yerel host kaynak ve oturum kimliği gerekli.")


@dataclass(frozen=True, slots=True)
class LocalObservation:
    """Observed yalnız sondanın çalışmasıdır; görev tamamlanması iddiası değildir."""

    host: LocalHost
    status: Literal["available", "unavailable", "observed"]
    snapshot_id: str | None = None
    results: tuple[ToolResult, ...] = ()
    message: str = ""


class LocalExecutor(Protocol):
    """Mevcut desktop araçlarını host context'i ile çağırır."""

    def __call__(
        self, name: str, args: ToolArgs, context: ToolContext
    ) -> Awaitable[ToolResult]: ...


class LocalComputer:
    """Whitelist salt okunur; click/type/shell yetkisi oluşturmaz."""

    def __init__(
        self,
        host: LocalHost,
        context: ToolContext,
        execute: LocalExecutor,
        permitted: Callable[[], bool],
        new_snapshot: Callable[[], int],
        cleanup: Callable[[str, ToolContext], Awaitable[None]],
    ) -> None:
        self._host, self._context, self._execute = host, context, execute
        self._permitted, self._new_snapshot = permitted, new_snapshot
        self._last_sequence = 0
        self._cleanup = cleanup
        self._lock = asyncio.Lock()

    def _unavailable(self, message: str) -> LocalObservation:
        return LocalObservation(self._host, "unavailable", message=message)

    async def invoke(self, operation: str) -> LocalObservation:
        """Status yan etkisizdir; snapshot mevcut iki desktop executor'ünü çağırır."""
        if operation not in {"status", "snapshot"}:
            return self._unavailable("Bilgisayar işlemi desteklenmiyor.")
        if self._host.platform != "darwin":
            return self._unavailable("Yerel bilgisayar sondası yalnız macOS destekliyor.")
        if not self._permitted():
            return self._unavailable("Yerel bilgisayar izni kapalı veya host oturumu geçersiz.")
        if operation == "status":
            return LocalObservation(self._host, "available")
        async with self._lock:
            return await self._snapshot()

    async def _snapshot(self) -> LocalObservation:
        sequence = self._new_snapshot()
        if type(sequence) is not int or sequence <= self._last_sequence:
            return self._unavailable("Snapshot sırası ilerlemiyor.")
        self._last_sequence = sequence
        identifier = f"{self._host.session_id}:{sequence}"
        owner = hashlib.sha256(
            f"{self._host.source_id}:{self._host.session_id}".encode()
        ).hexdigest()
        path = f".fusion/local-computer/{owner}.png"
        results = []
        observation = self._unavailable("Yerel sonda tamamlanmadı.")
        try:
            for name, args in (
                ("desktop_screenshot", {"path": path}),
                ("desktop_accessibility", {}),
            ):
                if not self._permitted():
                    break
                result = await self._execute(name, args, self._context)
                if not self._permitted():
                    break
                if not result.ok:
                    observation = self._unavailable(result.output)
                    break
                if name == "desktop_screenshot" and not result.images:
                    break
                results.append(result)
            if len(results) == 2:
                observation = LocalObservation(self._host, "observed", identifier, tuple(results))
        except Exception as error:
            self._diagnostic(error, "snapshot")
        finally:
            try:
                await self._cleanup(path, self._context)
            except Exception as error:
                self._diagnostic(error, "cleanup")
                observation = self._unavailable("Yerel sonda temizlenemedi.")
        if not self._permitted():
            return self._unavailable("Yerel bilgisayar izni kaldırıldı.")
        return observation

    def _diagnostic(self, error: Exception, operation: str) -> None:
        logging.getLogger(__name__).error(
            "Yerel bilgisayar sondası başarısız",
            extra={
                "error_type": type(error).__name__,
                "source_id": self._host.source_id,
                "session_id": self._host.session_id,
                "operation": operation,
            },
        )

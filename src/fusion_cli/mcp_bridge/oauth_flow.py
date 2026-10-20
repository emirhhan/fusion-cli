"""SDK'nın public OAuth akışını aynı depo kapsamında sıraya al."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from weakref import WeakKeyDictionary

import httpx

from .oauth_lease import AsyncLease, OAuthLease


class OAuthFlowOwner:
    """Mevcut havuzun sahibi olduğu, döngü ve depo bazlı kilitler."""

    def __init__(
        self, directory: Path | None = None, *, directory_factory: Callable[[], Path] | None = None
    ) -> None:
        self._directory = directory
        self._directory_factory = directory_factory
        self._locks: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, OAuthLease]] = (
            WeakKeyDictionary()
        )

    def lock_for(self, namespace: str) -> OAuthLease:
        """Farklı loop'ların async kilitlerini paylaşma."""
        loop = asyncio.get_running_loop()
        for expired in tuple(self._locks):
            if expired.is_closed():
                self._locks.pop(expired, None)
        locks = self._locks.setdefault(loop, {})
        if namespace not in locks:
            directory = self._directory_factory() if self._directory_factory else self._directory
            path = (
                directory / f"{hashlib.sha256(namespace.encode()).hexdigest()}.lock"
                if directory
                else None
            )
            locks[namespace] = OAuthLease(path)
        return locks[namespace]


class SerializedOAuth(httpx.Auth):
    """Her akış güncel depoyu yeniden yükleyen taze SDK sağlayıcısı kullanır."""

    # Kurulu OAuthClientProvider public sözleşmesi yanıt gövdesini ister.
    requires_response_body = True

    def __init__(self, lock: AsyncLease, factory: Callable[[], httpx.Auth]) -> None:
        self._lock = lock
        self._factory = factory

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        async with self._lock:
            flow = self._factory().async_auth_flow(request)
            try:
                outgoing = await anext(flow)
                while True:
                    response = yield outgoing
                    outgoing = await flow.asend(response)
            except StopAsyncIteration:
                return
            finally:
                await flow.aclose()

"""Public MCP stream ve notification API ile çağrı kimliğine bağlı iptal."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import cast

from anyio.abc import ObjectSendStream
from anyio.streams.memory import MemoryObjectSendStream
from mcp import ClientSession, types
from mcp.shared.message import SessionMessage


@dataclass(slots=True)
class CallScope:
    server: str
    request_id: int | str | None = None


class RequestTracker:
    """SDK'nın kendi JSON-RPC kimliği okunur; ikinci sayaç veya private hook yok."""

    def __init__(self) -> None:
        self._current: ContextVar[CallScope | None] = ContextVar("fusion_mcp_call", default=None)

    @contextmanager
    def track(self, server: str) -> Iterator[CallScope]:
        scope = CallScope(server)
        token = self._current.set(scope)
        try:
            yield scope
        finally:
            self._current.reset(token)

    def wrap(
        self, server: str, stream: ObjectSendStream[SessionMessage]
    ) -> MemoryObjectSendStream[SessionMessage]:
        # SDK imzası somut MemoryObjectSendStream der; kurulu BaseSession yalnız
        # public send/aclose sözleşmesini tüketir. Gerçek STDIO/HTTP testleri bunu ölçer.
        return cast(
            MemoryObjectSendStream[SessionMessage], _TrackedSendStream(server, stream, self)
        )

    def observe(self, server: str, message: SessionMessage) -> None:
        scope = self._current.get()
        request = message.message.root
        if (
            scope is not None
            and scope.server == server
            and isinstance(request, types.JSONRPCRequest)
            and request.method == "tools/call"
        ):
            scope.request_id = request.id


class _TrackedSendStream(ObjectSendStream[SessionMessage]):
    def __init__(
        self, server: str, stream: ObjectSendStream[SessionMessage], tracker: RequestTracker
    ) -> None:
        self._server, self._stream, self._tracker = server, stream, tracker

    async def send(self, item: SessionMessage) -> None:
        self._tracker.observe(self._server, item)
        await self._stream.send(item)

    async def aclose(self) -> None:
        await self._stream.aclose()


async def notify_cancel(session: ClientSession, scope: CallScope, timeout_seconds: float) -> None:
    """İptal bildirimi best effort'tür; uzaktaki etkinin geri alındığını iddia etmez."""
    if scope.request_id is None:
        return
    try:
        async with asyncio.timeout(timeout_seconds):
            await session.send_notification(
                types.ClientNotification(
                    types.CancelledNotification(
                        params=types.CancelledNotificationParams(
                            requestId=scope.request_id, reason="Fusion çağrıyı durdurdu."
                        )
                    )
                )
            )
    except Exception as error:
        logging.getLogger(__name__).warning(
            "MCP iptal bildirimi iletilemedi", extra={"hata": type(error).__name__}
        )

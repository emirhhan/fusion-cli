"""WebSocket MCP taşıması (`type: "ws"`; #241).

Claude Code `ws` girdisini yalnız JSON ile kabul eder ve kimlik doğrulama yalnız başlıkla
olur (`headers` / `headersHelper`). SDK'nın `websocket_client`'ı başlık almadığı için aynı
akış burada başlıklı kurulur. Yalnız `wss://` (ya da yerel makinede `ws://`) kabul edilir.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import anyio
from mcp import types
from mcp.shared.message import SessionMessage
from pydantic import ValidationError

from .types import McpConfigError

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def validate_ws_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme == "wss" and parts.hostname:
        return
    if parts.scheme == "ws" and parts.hostname in _LOCAL_HOSTS:
        return
    raise McpConfigError("WebSocket MCP adresi wss:// olmalı (ws:// yalnız yerel makinede)")


@asynccontextmanager
async def ws_streams(url: str, headers: dict[str, str] | None) -> AsyncIterator[tuple[Any, Any]]:
    validate_ws_url(url)
    try:
        from websockets.asyncio.client import connect
        from websockets.typing import Subprotocol
    except ImportError as error:  # pragma: no cover - kurulum eksikse
        raise McpConfigError("WebSocket MCP için `websockets` paketi gerekli") from error
    reader_tx, reader_rx = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    writer_tx, writer_rx = anyio.create_memory_object_stream[SessionMessage](0)
    async with connect(
        url, subprotocols=[Subprotocol("mcp")], additional_headers=headers or None
    ) as socket:

        async def _read() -> None:
            async with reader_tx:
                async for raw in socket:
                    try:
                        message = types.JSONRPCMessage.model_validate_json(raw)
                        await reader_tx.send(SessionMessage(message))
                    except ValidationError as exc:
                        await reader_tx.send(exc)

        async def _write() -> None:
            async with writer_rx:
                async for item in writer_rx:
                    await socket.send(
                        item.message.model_dump_json(by_alias=True, exclude_none=True)
                    )

        async with anyio.create_task_group() as group:
            group.start_soon(_read)
            group.start_soon(_write)
            yield reader_rx, writer_tx
            group.cancel_scope.cancel()

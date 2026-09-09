"""MCP taşıma ayrıntılarını istemci yaşam döngüsünden ayır."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from ..config.models import McpServerConfig, McpTransport


@asynccontextmanager
async def open_mcp_stream(
    config: McpServerConfig, *, auth: httpx.Auth | None = None
) -> AsyncIterator[tuple[Any, Any]]:
    """Yapılandırılmış taşımanın okuma/yazma akışlarını aç."""
    if config.transport is McpTransport.STDIO:
        if not config.command:
            raise ValueError("stdio MCP bağlantısı için komut gerekli")
        params = StdioServerParameters(command=config.command, args=list(config.args))
        async with stdio_client(params) as streams:
            yield streams
        return

    if not config.url:
        raise ValueError("HTTP MCP bağlantısı için URL gerekli")
    async with streamablehttp_client(config.url, auth=auth) as streams:
        read, write, _session_id = streams
        yield read, write

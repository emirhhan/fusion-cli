"""MCP taşıma ayrıntılarını istemci yaşam döngüsünden ayır."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from ..config.models import McpServerConfig, McpTransport

_SECRET_ARGUMENT_PREFIX = "__FUSION_SECRET__:"


def resolve_stdio_args(
    config: McpServerConfig, *, environ: Mapping[str, str] | None = None
) -> list[str]:
    """Şifreli ortam başvurularını yalnız alt-süreç başlatılırken çöz."""
    source = os.environ if environ is None else environ
    allowed = set(config.env_names)
    resolved: list[str] = []
    for argument in config.args:
        if not argument.startswith(_SECRET_ARGUMENT_PREFIX):
            resolved.append(argument)
            continue
        name = argument.removeprefix(_SECRET_ARGUMENT_PREFIX)
        if name not in allowed:
            raise ValueError(f"MCP gizli argümanı yapılandırılmamış: {name}")
        value = source.get(name, "")
        if not value:
            raise ValueError(f"MCP gizli argümanı bulunamadı: {name}")
        resolved.append(value)
    return resolved


@asynccontextmanager
async def open_mcp_stream(
    config: McpServerConfig, *, auth: httpx.Auth | None = None
) -> AsyncIterator[tuple[Any, Any]]:
    """Yapılandırılmış taşımanın okuma/yazma akışlarını aç."""
    if config.transport is McpTransport.STDIO:
        if not config.command:
            raise ValueError("stdio MCP bağlantısı için komut gerekli")
        params = StdioServerParameters(command=config.command, args=resolve_stdio_args(config))
        async with stdio_client(params) as streams:
            yield streams
        return

    if not config.url:
        raise ValueError("HTTP MCP bağlantısı için URL gerekli")
    async with streamablehttp_client(config.url, auth=auth) as streams:
        read, write, _session_id = streams
        yield read, write

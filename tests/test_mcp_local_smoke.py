"""Gerçek yerel SDK taşıması: kontrollü STDIO alt süreci ve loopback HTTP."""

from __future__ import annotations

import asyncio
import os
import socket
import sys

import pytest

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.core.constants import MCP_NETWORK_TIMEOUT_S
from fusion_cli.mcp_bridge.client import McpClient


async def test_real_stdio_child_is_reaped_after_read():
    script = """
import os
from mcp.server.fastmcp import FastMCP
server = FastMCP("offline-fixture", log_level="ERROR")
@server.tool()
def process_id() -> str:
    return str(os.getpid())
server.run(transport="stdio")
"""
    config = McpServerConfig("offline-stdio", command=sys.executable, args=("-c", script))
    async with McpClient((config,), interactive=False) as client:
        tools = await client.list_tools(config.name)
        assert [tool.name for tool in tools] == ["process_id"]
        result = await client.call(config.name, "process_id", {})
        assert result.ok
        assert result.structured is not None
        pid = int(result.structured["result"])
        assert pid != os.getpid()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_real_loopback_http_reads_and_cancels_pending_call(monkeypatch):
    import uvicorn
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("offline-fixture", log_level="ERROR", json_response=True)
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    @server.tool()
    async def pending_read() -> str:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return "ulaşılamaz"

    @server.tool()
    def read() -> str:
        return "gerçek yerel okuma"

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    service = uvicorn.Server(uvicorn.Config(server.streamable_http_app(), log_level="error"))
    owned = asyncio.create_task(service.serve(sockets=[sock]))
    monkeypatch.setenv("FUSION_OFFLINE_MCP_FIXTURE", "offline-fixture")
    config = McpServerConfig(
        "offline-http",
        transport=McpTransport.STREAMABLE_HTTP,
        url=f"http://127.0.0.1:{port}/mcp",
        token_env="FUSION_OFFLINE_MCP_FIXTURE",
    )
    try:
        async with asyncio.timeout(MCP_NETWORK_TIMEOUT_S):
            while not service.started:
                if owned.done():
                    owned.result()
                await asyncio.sleep(0)
        async with McpClient((config,), interactive=False) as client:
            assert {tool.name for tool in await client.list_tools(config.name)} == {
                "pending_read",
                "read",
            }
            assert (await client.call(config.name, "read", {})).structured == {
                "result": "gerçek yerel okuma"
            }
            pending = asyncio.create_task(client.call(config.name, "pending_read", {}))
            try:
                async with asyncio.timeout(MCP_NETWORK_TIMEOUT_S):
                    await entered.wait()
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
                async with asyncio.timeout(MCP_NETWORK_TIMEOUT_S):
                    await cancelled.wait()
                assert client.statuses[config.name].state == "degraded"
                assert (await client.call(config.name, "read", {})).ok
                assert client.statuses[config.name].state == "bagli"
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    finally:
        service.should_exit = True
        try:
            async with asyncio.timeout(MCP_NETWORK_TIMEOUT_S):
                await owned
        finally:
            if not owned.done():
                owned.cancel()
                await asyncio.gather(owned, return_exceptions=True)
            sock.close()

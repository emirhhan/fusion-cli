"""Production smoke kabulü: stdout yerine gerçek yerel protokol ve dosya kanıtı."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ListToolsResult, TextContent

MCP_TIMEOUT_SECONDS = 15
LARGE_SHA256 = "70840c06abe530b3cc3ab00c411a94d86705cdaf322e8c8ede5c5b1b611c6b39"


class _SmokeClient(Protocol):
    async def list_tools(self) -> ListToolsResult: ...
    async def call_tool(self, name: str, arguments: dict[str, object]) -> CallToolResult: ...


def _measured_client(session: ClientSession) -> tuple[_SmokeClient, Callable[[], bool]]:
    listed = False
    called = False

    class MeasuredClient:
        __slots__ = ()

        async def list_tools(self) -> ListToolsResult:
            nonlocal listed
            result = await session.list_tools()
            listed = any(tool.name == "ping" for tool in result.tools)
            return result

        async def call_tool(self, name: str, arguments: dict[str, object]) -> CallToolResult:
            nonlocal called
            result = await session.call_tool(name, arguments)
            called = (
                listed
                and name == "ping"
                and not result.isError
                and any(
                    isinstance(item, TextContent) and item.text == "pong" for item in result.content
                )
            )
            return result

    # Kabul kaydı adayın yazabildiği nesnenin alanı değildir; sahibi harness'tir.
    return MeasuredClient(), lambda: listed and called


async def check_mcp(root: Path) -> None:
    """Aday fonksiyonu gerçek sırsız stdio oturumunda listeleme ve çağırma yapmalı."""
    spec = importlib.util.spec_from_file_location("candidate_smoke", root / "smoke_test.py")
    if spec is None or spec.loader is None:
        raise ValueError("smoke_test.py okunamadı.")
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    smoke = getattr(candidate, "smoke", None)
    if not callable(smoke):
        raise ValueError("smoke_test.py içinde async smoke(client) gerekli.")
    server = Path(__file__).with_name("oauth_mcp_server.py")
    parameters = StdioServerParameters(command=sys.executable, args=[str(server), "--stdio"])
    async with (
        asyncio.timeout(MCP_TIMEOUT_SECONDS),
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        await session.initialize()
        client, completed = _measured_client(session)
        await smoke(client)
        if not completed():
            raise ValueError("Gerçek MCP list_tools ve ping çağrısı gözlenmedi.")


def check_large(root: Path) -> None:
    """Yalnız TARGET değişmeli; büyük dosyanın diğer tüm baytları korunmalı."""
    digest = hashlib.sha256((root / "large.py").read_bytes()).hexdigest()
    if digest != LARGE_SHA256:
        raise ValueError("Büyük dosya eksik, bozuk veya TARGET dışında değiştirilmiş.")


def main() -> None:
    if sys.argv[1:] == ["mcp"]:
        asyncio.run(check_mcp(Path.cwd()))
    elif sys.argv[1:] == ["large"]:
        check_large(Path.cwd())
    else:
        raise SystemExit("Kabul türü mcp veya large olmalı.")


if __name__ == "__main__":
    main()

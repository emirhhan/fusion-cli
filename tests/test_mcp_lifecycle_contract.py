"""Paket 6: gerçek istemci akışında çevrimdışı list/call/close sınırları.

Süreler ürün varsayılanı değildir: küçük test bütçesi ve on kat büyük emniyet
sınırı, hiç cevap vermeyen SDK doubles ile eksik deadline'ı ölçer.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge import client as client_module
from fusion_cli.mcp_bridge.client import McpClient

TEST_BUDGET_SECONDS = 0.01
WATCHDOG_SECONDS = TEST_BUDGET_SECONDS * 10


@pytest.fixture(autouse=True)
def izole_kalici_bellek() -> None:
    """Bu dosya bellek kullanmaz; ağır global temizleyiciyi yükleme."""


@dataclass
class OfflineSession:
    """Ağ/süreç açmadan SDK sınırını temsil et; beklemeler iptal edilebilir."""

    hanging_stage: str
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def __aenter__(self) -> OfflineSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self.hanging_stage == "close":
            await self.release.wait()

    async def initialize(self) -> None:
        pass

    async def list_tools(self, cursor: str | None = None) -> ListToolsResult:
        if self.hanging_stage == "list":
            await self.release.wait()
        return ListToolsResult(tools=[])

    async def call_tool(self, name: str, args: dict[str, object]) -> CallToolResult:
        if self.hanging_stage == "call":
            await self.release.wait()
        return CallToolResult(content=[TextContent(type="text", text="tamam")])


@asynccontextmanager
async def offline_stream(*args: object, **kwargs: object) -> AsyncIterator[tuple[None, None]]:
    """Gerçek transport çağrısı yerine yalnız yerel bağlam ver."""
    yield None, None


async def finishes_without_watchdog(operation: Awaitable[object]) -> bool:
    """Ürün deadline'ı ile dış test iptalini ayır; tüm görevleri sahiplen."""
    task = asyncio.create_task(operation)
    try:
        await asyncio.wait_for(asyncio.shield(task), WATCHDOG_SECONDS)
        return True
    except TimeoutError:
        return task.done()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("stage", ["list", "call", "close"])
async def test_hanging_operation_has_its_own_deadline(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    session = OfflineSession(stage)
    monkeypatch.setattr(client_module, "ClientSession", lambda *_streams: session)
    monkeypatch.setattr(client_module, "open_mcp_stream", offline_stream)
    config = McpServerConfig(
        name="offline",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://offline.invalid/mcp",
        token_env="OFFLINE_UNUSED_TOKEN",
    )
    client = McpClient([config], timeout_seconds=TEST_BUDGET_SECONDS, interactive=False)
    await client.__aenter__()
    try:
        if stage == "list":
            operation = client.list_tools("offline")
        elif stage == "call":
            operation = client.call("offline", "read", {})
        else:
            operation = client.__aexit__()
        assert await finishes_without_watchdog(operation), (
            f"{stage} ürün bütçesinde sonlanmadı; yalnız test emniyet iptali durdurdu"
        )
    finally:
        session.release.set()
        await client.__aexit__()


async def test_offline_public_client_preserves_successful_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = OfflineSession("none")
    monkeypatch.setattr(client_module, "ClientSession", lambda *_streams: session)
    monkeypatch.setattr(client_module, "open_mcp_stream", offline_stream)
    config = McpServerConfig(
        name="offline",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://offline.invalid/mcp",
        token_env="OFFLINE_UNUSED_TOKEN",
    )
    async with McpClient([config], interactive=False) as client:
        assert await client.list_tools("offline") == []
        result = await client.call("offline", "read", {})
        assert result.ok
        assert result.output == "tamam"


async def test_server_call_budget_overrides_client_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sunucuya verilen kısa bütçe, başka sunucunun uzun varsayılanını kullanmaz."""
    session = OfflineSession("call")
    monkeypatch.setattr(client_module, "ClientSession", lambda *_streams: session)
    monkeypatch.setattr(client_module, "open_mcp_stream", offline_stream)
    config = McpServerConfig(
        name="offline",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://offline.invalid/mcp",
        token_env="OFFLINE_UNUSED_TOKEN",
        call_timeout_s=TEST_BUDGET_SECONDS,
    )
    async with McpClient(
        [config], timeout_seconds=WATCHDOG_SECONDS * 10, interactive=False
    ) as client:
        assert await finishes_without_watchdog(client.call("offline", "read", {}))

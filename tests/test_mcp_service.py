from __future__ import annotations

import asyncio

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.client import McpConnectionStatus
from fusion_cli.mcp_bridge.service import McpConnectionService


async def test_giris_arka_planda_baslar_ve_durum_sorgulanir() -> None:
    release = asyncio.Event()

    async def probe(_config: McpServerConfig) -> McpConnectionStatus:
        await release.wait()
        return McpConnectionStatus(server="meta", state="bagli", tool_count=4)

    service = McpConnectionService(probe=probe)
    config = McpServerConfig(
        name="meta",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.example.com/mcp",
    )

    started = service.start_login(config)
    assert started.state == "giris_bekleniyor"
    assert service.login_status("meta").state == "giris_bekleniyor"

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert service.login_status("meta").state == "bagli"
    await service.close()


async def test_ayni_baglanti_icin_ikinci_giris_gorevi_acilmaz() -> None:
    blocker = asyncio.Event()

    async def probe(_config: McpServerConfig) -> McpConnectionStatus:
        await blocker.wait()
        return McpConnectionStatus(server="meta", state="bagli")

    service = McpConnectionService(probe=probe)
    config = McpServerConfig(name="meta", command="x")

    service.start_login(config)
    first = service.pending_task("meta")
    service.start_login(config)

    assert service.pending_task("meta") is first
    blocker.set()
    await service.close()

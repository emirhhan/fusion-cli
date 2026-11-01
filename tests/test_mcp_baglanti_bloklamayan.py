"""Bloklamayan MCP açılışı (#239): `MCP_CONNECTION_NONBLOCKING`, `MCP_CONNECT_TIMEOUT_MS`.

Claude Code: sunucular varsayılan olarak arka planda bağlanır; bekleme 5 sn ile
sınırlıdır; `MCP_CONNECTION_NONBLOCKING=0` açılışı bütün sunucuları beklemeye zorlar.
"""

from __future__ import annotations

import asyncio

from fusion_cli.config.models import McpServerConfig
from fusion_cli.mcp_bridge import pool as pool_module
from fusion_cli.mcp_bridge.pool import McpToolPool
from fusion_cli.mcp_bridge.timeouts import connect_wait_s, connection_nonblocking

from .test_mcp_pool import _FakeClient


def test_ortam_degiskenleri():
    assert connection_nonblocking({}) is True
    assert connection_nonblocking({"MCP_CONNECTION_NONBLOCKING": "0"}) is False
    assert connection_nonblocking({"MCP_CONNECTION_NONBLOCKING": "false"}) is False
    assert connect_wait_s({}) == 5.0
    assert connect_wait_s({"MCP_CONNECT_TIMEOUT_MS": "250"}) == 0.25


def _yavas_istemci(serbest: asyncio.Event, kapandi: asyncio.Event):
    class _Yavas(_FakeClient):
        async def __aenter__(self):
            await serbest.wait()
            return self

        async def __aexit__(self, *_exc: object) -> None:
            kapandi.set()

    return _Yavas


async def test_gec_kalan_sunucu_arka_planda_baglanir_sonraki_turda_gelir(monkeypatch):
    serbest, kapandi = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(pool_module, "McpClient", _yavas_istemci(serbest, kapandi))
    monkeypatch.setenv("MCP_CONNECT_TIMEOUT_MS", "50")
    monkeypatch.delenv("MCP_CONNECTION_NONBLOCKING", raising=False)
    havuz = McpToolPool()
    config = (McpServerConfig(name="yavas", command="x"),)

    assert await havuz.clients_for(config) == ()

    serbest.set()
    ikinci = await havuz.clients_for(config)
    assert [client.name for client in ikinci] == ["yavas"]
    await havuz.aclose()
    assert kapandi.is_set()


async def test_bloklayan_kip_butun_sunuculari_bekler(monkeypatch):
    serbest, kapandi = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(pool_module, "McpClient", _yavas_istemci(serbest, kapandi))
    monkeypatch.setenv("MCP_CONNECT_TIMEOUT_MS", "50")
    monkeypatch.setenv("MCP_CONNECTION_NONBLOCKING", "0")
    havuz = McpToolPool()
    asyncio.get_running_loop().call_later(0.2, serbest.set)

    clients = await havuz.clients_for((McpServerConfig(name="yavas", command="x"),))

    assert [client.name for client in clients] == ["yavas"]
    await havuz.aclose()


async def test_baglanirken_kapatma_arka_plan_acilisini_sahipsiz_birakmaz(monkeypatch):
    serbest, kapandi = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(pool_module, "McpClient", _yavas_istemci(serbest, kapandi))
    monkeypatch.setenv("MCP_CONNECT_TIMEOUT_MS", "20")
    monkeypatch.delenv("MCP_CONNECTION_NONBLOCKING", raising=False)
    havuz = McpToolPool()

    config = McpServerConfig(name="yavas", command="x", close_timeout_s=0.05)
    await havuz.clients_for((config,))
    await havuz.aclose()

    assert havuz._connecting == {}


class _Defter:
    """`ToolRegistry`'nin bu testlere yeten kısmı."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def register_or_replace(self, tool) -> None:
        self.tools[tool.name] = tool

    def unregister_remote(self, name: str) -> bool:
        return self.tools.pop(name, None) is not None

    def get(self, name: str):
        return self.tools.get(name)


def _kayitli_yavas(serbest: asyncio.Event, kapandi: asyncio.Event):
    base = _yavas_istemci(serbest, kapandi)

    class _Kayitli(base):
        async def register_into(self, registry) -> tuple[str, ...]:
            from fusion_cli.core.tools import Tool, ToolResult

            async def _run(args, context):
                return ToolResult(output="ok")

            name = f"mcp__{self.name}__arac"
            registry.register_or_replace(
                Tool(name=name, description="", parameters={"type": "object"}, run=_run)
            )
            return (name,)

        async def catalog(self, server):
            from fusion_cli.mcp_bridge.references import McpCatalog

            return McpCatalog()

    return _Kayitli


def _taze_havuz(monkeypatch):
    from fusion_cli.mcp_bridge.late_connect import LateConnections

    monkeypatch.setattr(pool_module, "_POOL", McpToolPool())
    monkeypatch.setattr(pool_module, "_LATE", LateConnections())


async def test_tur_ortasinda_baglanan_sunucunun_araclari_ayni_turda_deftere_girer(monkeypatch):
    serbest, kapandi = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(pool_module, "McpClient", _kayitli_yavas(serbest, kapandi))
    monkeypatch.setenv("MCP_CONNECT_TIMEOUT_MS", "30")
    monkeypatch.delenv("MCP_CONNECTION_NONBLOCKING", raising=False)
    _taze_havuz(monkeypatch)
    defter = _Defter()
    config = (McpServerConfig(name="yavas", command="x"),)

    assert await pool_module.ensure_mcp_tools(config, defter) == ()
    assert "WaitForMcpServers" in defter.tools
    assert "mcp__yavas__arac" not in defter.tools

    serbest.set()
    for _ in range(50):
        if "mcp__yavas__arac" in defter.tools:
            break
        await asyncio.sleep(0.01)

    assert "mcp__yavas__arac" in defter.tools
    assert "WaitForMcpServers" not in defter.tools
    await pool_module.close_mcp_pool()


async def test_wait_for_mcp_servers_baglanmayi_bekler_ve_durumu_yazar(monkeypatch):
    serbest, kapandi = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(pool_module, "McpClient", _kayitli_yavas(serbest, kapandi))
    monkeypatch.setenv("MCP_CONNECT_TIMEOUT_MS", "20")
    monkeypatch.delenv("MCP_CONNECTION_NONBLOCKING", raising=False)
    _taze_havuz(monkeypatch)
    defter = _Defter()
    await pool_module.ensure_mcp_tools((McpServerConfig(name="yavas", command="x"),), defter)
    wait_tool = defter.tools["WaitForMcpServers"]
    assert "yavas" in wait_tool.description
    asyncio.get_running_loop().call_later(0.05, serbest.set)

    result = await wait_tool.run({}, None)

    assert "✔ yavas: bağlandı" in result.output
    assert "mcp__yavas__arac" in defter.tools
    await pool_module.close_mcp_pool()


async def test_always_load_sunucusu_sonuna_kadar_beklenir(monkeypatch):
    serbest, kapandi = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(pool_module, "McpClient", _yavas_istemci(serbest, kapandi))
    monkeypatch.setenv("MCP_CONNECT_TIMEOUT_MS", "20")
    monkeypatch.delenv("MCP_CONNECTION_NONBLOCKING", raising=False)
    havuz = McpToolPool()
    asyncio.get_running_loop().call_later(0.1, serbest.set)

    clients = await havuz.clients_for(
        (McpServerConfig(name="yavas", command="x", always_load=True),)
    )

    assert [client.name for client in clients] == ["yavas"]
    await havuz.aclose()

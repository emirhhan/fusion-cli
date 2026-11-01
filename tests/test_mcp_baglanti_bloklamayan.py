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

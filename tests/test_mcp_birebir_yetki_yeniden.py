"""Araç çağrısı 401/403 dönünce headersHelper yeniden çalışır, çağrı bir kez yinelenir (#249)."""

from __future__ import annotations

from types import SimpleNamespace

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.core.tools import ToolResult
from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.mcp_bridge.egress import guarded_client_factory
from fusion_cli.mcp_bridge.failures import STATE_LOGIN_REQUIRED


def _config(helper: str = "/bin/yardimci") -> McpServerConfig:
    return McpServerConfig(
        name="api",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://api.example.com/mcp",
        headers_helper=helper,
    )


async def test_yanit_kancasi_durum_kodunu_bildirir():
    seen: list[int] = []
    client = guarded_client_factory("https://api.example.com/mcp", on_response=seen.append)()

    await client.event_hooks["response"][0](SimpleNamespace(status_code=401))
    await client.aclose()

    assert seen == [401]


class _Taze:
    def __init__(self, result: ToolResult | Exception) -> None:
        self.result = result
        self.calls = 0
        self._statuses: dict[str, object] = {}
        self._successor = None

    async def call(self, server, name, args):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _eski(config: McpServerConfig, fresh: _Taze) -> McpClient:
    client = McpClient((config,))

    async def _fail(server, name, args):
        client._auth_failures.observer(server)(401)
        raise RuntimeError("Connection closed")

    async def _reauth(name):
        return fresh

    client.call = _fail  # type: ignore[method-assign]
    client.reauth = _reauth
    return client


async def test_401_sonrasi_yeniden_baglanip_bir_kez_dener():
    fresh = _Taze(ToolResult(output="tamam"))
    client = _eski(_config(), fresh)
    run = client._make_run("api", "ara")

    first = await run({}, None)  # type: ignore[arg-type]
    second = await run({}, None)  # type: ignore[arg-type]

    assert first.output == "tamam" and fresh.calls == 2  # sonraki çağrı yeni istemciye gider
    assert second.output == "tamam"


async def test_yardimci_yoksa_ya_da_tekrar_basarisizsa():
    no_helper = _eski(_config(helper=""), _Taze(ToolResult(output="x")))
    failing_fresh = _Taze(RuntimeError("yine 401"))
    failing = _eski(_config(), failing_fresh)

    plain = await no_helper._make_run("api", "ara")({}, None)  # type: ignore[arg-type]
    again = await failing._make_run("api", "ara")({}, None)  # type: ignore[arg-type]

    assert not plain.ok and "MCP aracı hatası" in plain.output
    assert not again.ok and failing_fresh.calls == 1
    assert failing_fresh._statuses["api"].state == STATE_LOGIN_REQUIRED

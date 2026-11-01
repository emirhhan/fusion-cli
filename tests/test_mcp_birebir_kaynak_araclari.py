"""Kaynak listeleme/okuma araçları (#255)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fusion_cli.mcp_bridge.references import McpCatalog, McpResource
from fusion_cli.mcp_bridge.resource_tools import LIST_TOOL, READ_TOOL, register_resource_tools
from fusion_cli.tools import ToolRegistry


class _Istemci:
    servers = ("docs", "yok")

    def has_resources(self, server):
        return server == "docs"

    async def catalog(self, server):
        return McpCatalog(
            resources=(
                McpResource("docs", "file:///a.md", "A"),
                McpResource("docs", "ui://panel", "UI"),
            )
        )

    async def read_resource(self, server, uri):
        return f"içerik {uri}"


def test_kaynak_araclari_yalniz_kaynakli_sunucuda_kaydedilir_ve_calisir():
    defter = ToolRegistry()
    assert register_resource_tools(_Istemci(), defter) == (LIST_TOOL, READ_TOOL)
    liste = asyncio.run(defter.get(LIST_TOOL).run({}, SimpleNamespace()))
    assert "file:///a.md" in liste.output and "ui://" not in liste.output
    oku = asyncio.run(defter.get(READ_TOOL).run({"server": "docs", "uri": "file:///a.md"}, None))
    assert oku.output == "içerik file:///a.md"
    hata = asyncio.run(defter.get(READ_TOOL).run({"server": "yok", "uri": "x"}, None))
    assert not hata.ok
    bos = ToolRegistry()
    istemci = _Istemci()
    istemci.has_resources = lambda server: False
    assert register_resource_tools(istemci, bos) == ()

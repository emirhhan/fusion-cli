"""Sunucu talimatları, açıklama sınırları, tools/list_changed (#256, #262, #263)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mcp.types import ServerNotification, ToolListChangedNotification

from fusion_cli.config.models import McpServerConfig
from fusion_cli.mcp_bridge import reference_service
from fusion_cli.mcp_bridge.references import catalog_change_handler
from fusion_cli.mcp_bridge.schema import clean_description, description_limit
from fusion_cli.tools import ToolRegistry


def test_aciklama_siniri_4096_ve_ortam_degiskeni():
    assert len(clean_description("y" * 9000)) == 4096
    assert description_limit(deferred=True, environ={}) == 16384
    assert description_limit(environ={"CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH": "100"}) == 100
    assert description_limit(environ={"CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH": "abc"}) == 4096


def test_sunucu_talimatlari_claude_bicimiyle_baglama_girer(monkeypatch):
    client = SimpleNamespace(server_instructions=lambda name: "Önce search aracını kullan.")
    monkeypatch.setattr(reference_service, "connected_mcp_client", lambda name: client)
    configs = (McpServerConfig("docs", "c"),)
    sonuc = asyncio.run(reference_service.expand_mcp_references("merhaba", configs))
    assert sonuc.task == "merhaba"
    assert sonuc.context == ""
    selected = reference_service.server_instructions_block(configs)
    assert selected.startswith("# MCP Server Instructions")
    assert '<mcp_instructions server="docs">' in selected
    assert "Önce search aracını kullan." in selected
    assert "Untrusted" in selected


def test_tools_list_changed_bildirimi_isaretler():
    olaylar: list[str] = []
    handler = catalog_change_handler(
        lambda: olaylar.append("katalog"), lambda: olaylar.append("arac")
    )
    bildirim = ServerNotification(
        ToolListChangedNotification(method="notifications/tools/list_changed")
    )
    asyncio.run(handler(bildirim))
    assert olaylar == ["arac"]


def test_kalkan_uzak_arac_defterden_cikar_yerel_kalir():
    from fusion_cli.core.tools import Tool, ToolResult

    async def _run(args, ctx):
        return ToolResult(output="")

    defter = ToolRegistry()
    defter.register(Tool(name="yerel", description="", parameters={}, run=_run))
    defter.register_or_replace(Tool(name="mcp__s__a", description="", parameters={}, run=_run))
    assert defter.unregister_remote("mcp__s__a") is True
    assert defter.unregister_remote("yerel") is False
    assert defter.get("yerel") is not None

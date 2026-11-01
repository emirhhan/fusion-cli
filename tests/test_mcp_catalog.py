from fusion_cli.appserver.mcp_catalog import project_tools
from fusion_cli.core.tools import ToolEffect
from fusion_cli.mcp_bridge.types import RemoteTool


def test_arac_katalogu_kaynagi_etkiyi_ve_parametreleri_ayri_gosterir():
    tools = [
        RemoteTool(
            "one",
            "lookup",
            "Find a document",
            {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search text"}},
                "required": ["query"],
            },
            ToolEffect.REMOTE_READ,
        ),
        RemoteTool("two", "lookup", "Update", {}, ToolEffect.REMOTE_WRITE),
    ]
    result = project_tools(tools)
    assert [item["name"] for item in result["tools"]] == ["mcp__one__lookup", "mcp__two__lookup"]
    assert result["tools"][0]["effect"] == "remote_read"
    assert result["tools"][0]["parameters"][0] == {
        "name": "query",
        "type": "string",
        "required": True,
        "description": "Search text",
    }


def test_katalog_sirli_aciklamayi_ve_ornek_varsayilan_degerlerini_tasimiz():
    result = project_tools(
        [
            RemoteTool(
                "one",
                "lookup",
                "password=SENTINEL_SECRET",
                {
                    "properties": {
                        "query": {
                            "type": "string",
                            "default": "SENTINEL_DEFAULT",
                            "examples": ["SENTINEL_EXAMPLE"],
                            "description": "token=SENTINEL_PARAM",
                        }
                    },
                },
            )
        ]
    )
    assert "SENTINEL" not in str(result)
    assert result["tools"][0]["description"]
    assert "default" not in str(result)


def test_katalog_sinirlidir_bozuk_parametre_taniminda_cokmez():
    tools = [
        RemoteTool("one", f"tool-{i}", "", {"properties": {"bad": None}, "required": None})
        for i in range(205)
    ]
    result = project_tools(tools)
    assert len(result["tools"]) == 200
    assert result["total"] == 205
    assert result["truncated"] is True


async def test_katalog_mevcut_istemciyi_girissiz_acar_ve_arac_calistirmaz(monkeypatch):
    from fusion_cli.appserver import mcp_catalog
    from fusion_cli.config.models import McpServerConfig
    from fusion_cli.mcp_bridge.types import McpConnectionStatus

    calls = []

    class Client:
        def __init__(self, configs, *, interactive):
            assert interactive is False
            self.statuses = {"one": McpConnectionStatus("one", "bagli")}
            calls.append("open")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            calls.append("close")

        async def list_tools(self, server):
            calls.append("list")
            return [RemoteTool(server, "lookup", "Search", {})]

    monkeypatch.setattr(mcp_catalog, "McpClient", Client)
    result = await mcp_catalog.list_tool_catalog(McpServerConfig(name="one", command="fake"))
    assert result["ok"] is True
    assert calls == ["open", "list", "close"]


async def test_takilan_mcp_sunucusu_katalog_rpc_sini_sonsuza_dek_bekletmez():
    """Ölçüldü (30 Ekim, S2-28): sunucu başlatma ve `list_tools` zaman aşımsızdı."""
    import asyncio

    from fusion_cli.appserver import mcp_catalog
    from fusion_cli.config.models import McpServerConfig

    class Takilan:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            await asyncio.Event().wait()

        async def __aexit__(self, *_args):
            return None

    original = mcp_catalog.McpClient
    mcp_catalog.McpClient = Takilan
    try:
        sonuc = await mcp_catalog.list_tool_catalog(
            McpServerConfig(name="one", command="fake"), timeout=0.2
        )
    finally:
        mcp_catalog.McpClient = original

    assert sonuc["ok"] is False and "zamanında" in sonuc["metin"]


async def test_katalog_istem_ve_kaynaklari_sohbet_yazimiyla_doner(monkeypatch):
    """Ölçüldü (31 Ekim): Bağlantılar kataloğu yalnız araçları döndürüyordu; MCP istemleri ve
    kaynakları masaüstünde sunucu başına görünmüyordu. İstem listesi hatası araçları düşürmez."""
    from fusion_cli.appserver import mcp_catalog
    from fusion_cli.config.models import McpServerConfig
    from fusion_cli.mcp_bridge.references import (
        McpCatalog,
        McpPrompt,
        McpPromptArgument,
        McpResource,
    )

    class _Client:
        fail = False

        def __init__(self, configs, **kwargs) -> None:
            self.statuses = {"gh": type("S", (), {"state": "bagli"})()}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def list_tools(self, server: str):
            return []

        async def catalog(self, server: str) -> McpCatalog:
            if _Client.fail:
                raise TimeoutError
            return McpCatalog(
                prompts=(
                    McpPrompt("gh", "review-pr", "İncele", (McpPromptArgument("n", "", True),)),
                ),
                resources=(McpResource("gh", "repo://a", name="A deposu"),),
            )

    monkeypatch.setattr(mcp_catalog, "McpClient", _Client)
    server = McpServerConfig(name="gh", command="npx")

    result = await mcp_catalog.list_tool_catalog(server)
    _Client.fail = True
    degraded = await mcp_catalog.list_tool_catalog(server)

    assert result["ok"] is True
    assert result["prompts"] == [
        {"command": "/mcp__gh__review-pr", "usage": "<n>", "description": "İncele"}
    ]
    assert result["resources"] == [{"mention": "@gh:repo://a", "name": "A deposu", "mimeType": ""}]
    assert degraded["ok"] is True and degraded["prompts"] == [] and degraded["resources"] == []

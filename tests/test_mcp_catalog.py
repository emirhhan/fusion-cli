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
    assert [item["name"] for item in result["tools"]] == ["one__lookup", "two__lookup"]
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

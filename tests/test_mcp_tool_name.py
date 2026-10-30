"""MCP araç adı sağlayıcı kuralına uyar: `^[a-zA-Z0-9_-]{1,64}$`.

Ölçüldü (30 Ekim): `f"{server}__{tool}"` ham birleştiriliyordu; ayarda "META ADS"
gibi boşluklu sunucu adı ya da 64+ karakterlik ad OpenAI/Anthropic/Gemini'de 400
hatası verip bütün turu düşürebilir (M1-10).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.mcp_bridge.tool_name import MAX_TOOL_NAME_CHARS, fusion_tool_name
from fusion_cli.tools import ToolRegistry

_RULE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def test_gecerli_ad_degismez():
    assert fusion_tool_name("fusion", "list_dir") == "fusion__list_dir"


def test_bosluk_ve_nokta_temizlenir_ve_kurala_uyar():
    name = fusion_tool_name("META ADS", "get.campaigns v2")

    assert _RULE.match(name)
    assert " " not in name


def test_temizlik_farkli_adlari_ayni_ada_cevirmez():
    assert fusion_tool_name("A B", "x") != fusion_tool_name("A_B", "x")
    assert fusion_tool_name("a b", "x") == fusion_tool_name("a b", "x")


def test_uzun_ad_siniri_asmaz_ve_ayirt_edilir():
    one = fusion_tool_name("s" * 40, "a" * 60)
    two = fusion_tool_name("s" * 40, "a" * 59 + "b")

    assert len(one) <= MAX_TOOL_NAME_CHARS and _RULE.match(one)
    assert one != two


class _Arac:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = ""
        self.inputSchema: dict[str, object] = {}
        self.annotations = None


class _Oturum:
    async def list_tools(self, cursor=None):
        return SimpleNamespace(tools=[_Arac("get campaigns")], nextCursor=None)


async def test_register_into_kuralsiz_adi_kayit_defterine_temiz_yazar():
    client = McpClient(())
    client._sessions["META ADS"] = _Oturum()
    registry = ToolRegistry()

    eklenen = await client.register_into(registry)

    assert len(eklenen) == 1
    assert _RULE.match(eklenen[0])
    assert registry.get(eklenen[0]) is not None

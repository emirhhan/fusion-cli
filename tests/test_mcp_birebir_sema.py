"""MCP şema alan açıklaması 300 karakterde kesilmez (#262).

Belge (code.claude.com/docs/en/mcp, "Change the description length limits"): yalnız sunucu
talimatı ve araç açıklaması 4.096 (araç aramasıyla 16.384) karakterle sınırlı;
`CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` ikisini de değiştirir. Alan başına ayrı sınır yok.
"""

from __future__ import annotations

from fusion_cli.mcp_bridge.schema import simplify_schema


def _field(text: str) -> object:
    schema = {"type": "object", "properties": {"q": {"type": "string", "description": text}}}
    return simplify_schema(schema)["properties"]["q"]["description"]  # type: ignore[index]


def test_alan_aciklamasi_300_ile_kesilmez(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH", raising=False)

    assert _field("a" * 1_000) == "a" * 1_000
    assert len(_field("b" * 5_000)) == 4_096


def test_alan_aciklamasi_ortam_sinirina_uyar(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH", "500")

    assert len(_field("c" * 800)) == 500


# --- Ham şema Anthropic'e, sade şema diğer sağlayıcılara (#262) -----------------------------

_HAM = {
    "type": "object",
    "$defs": {"Kisi": {"type": "object", "properties": {"ad": {"type": "string"}}}},
    "properties": {
        "kim": {"$ref": "#/$defs/Kisi"},
        "deger": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        "not": {"type": "string", "description": "<important>gizli</important>açık"},
    },
}


def _istek_araclari(model: str):
    from dataclasses import replace

    from fusion_cli.core.tool_schema_variants import remember_raw_schema
    from fusion_cli.mcp_bridge.client import _raw_schema
    from fusion_cli.providers.litellm_provider import LiteLlmProvider

    from .fakes import request

    sade = simplify_schema(_HAM)
    remember_raw_schema("mcp__s__ara", sade, _raw_schema(_HAM))
    araclar = (
        {"type": "function", "function": {"name": "mcp__s__ara", "parameters": sade}},
        {"type": "function", "function": {"name": "Read", "parameters": {"type": "object"}}},
    )
    provider = LiteLlmProvider(model, role="agent")
    kwargs = provider._call_kwargs(replace(request(), tools=araclar), stream=False)
    return {tool["function"]["name"]: tool["function"]["parameters"] for tool in kwargs["tools"]}


def test_anthropic_modeline_ham_sema_gider_aciklama_temizlenir():
    params = _istek_araclari("anthropic/claude-sonnet-4-5")["mcp__s__ara"]

    assert params["properties"]["kim"] == {"$ref": "#/$defs/Kisi"}
    assert "$defs" in params
    assert "anyOf" in params["properties"]["deger"]
    assert params["properties"]["not"]["description"] == "açık"


def test_diger_saglayicilara_sade_sema_gider():
    params = _istek_araclari("gemini/gemini-2.5-pro")["mcp__s__ara"]

    assert "$defs" not in params
    assert "anyOf" not in params["properties"]["deger"]


def test_sema_degisirse_eski_ham_sema_kullanilmaz():
    from fusion_cli.core.tool_schema_variants import remember_raw_schema, with_raw_schemas

    remember_raw_schema("mcp__s__b", {"type": "object", "properties": {}}, _HAM)
    yeni = {"type": "object", "properties": {"x": {"type": "string"}}}
    tools = with_raw_schemas(
        [{"type": "function", "function": {"name": "mcp__s__b", "parameters": yeni}}]
    )

    assert tools[0]["function"]["parameters"] == yeni


def test_ham_sema_yalniz_anthropic_yolundaki_claude_modellerine():
    """Yerel/üçüncü taraf sağlayıcıda adı 'claude' geçen model ham şema almaz."""
    from fusion_cli.core.tool_schema_variants import accepts_raw_schemas

    for model in (
        "claude-opus-4-1",
        "anthropic/claude-sonnet-4-5",
        "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
        "vertex_ai/claude-sonnet-4@20250514",
        "openrouter/anthropic/claude-sonnet-4",
    ):
        assert accepts_raw_schemas(model), model
    for model in ("ollama/claude-distill:7b", "lm_studio/claude-like", "gemini/gemini-2.5-flash"):
        assert not accepts_raw_schemas(model), model

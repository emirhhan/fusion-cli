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

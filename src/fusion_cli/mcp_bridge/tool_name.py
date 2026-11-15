"""Uzak MCP aracının kayıt/sağlayıcı adı: `mcp__<sunucu>__<araç>` (#242).

Kural `core/mcp_tool_names.py`'de: geçersiz karakter `_`, 128'i aşan ad dışarıda
(None), 65-128 arası ad sağlayıcı sınırı (64) için özetle kısalır.
"""

from __future__ import annotations

from ..core.mcp_tool_names import MAX_PROVIDER_TOOL_NAME_CHARS, provider_mcp_tool_name

__all__ = ["MAX_TOOL_NAME_CHARS", "fusion_tool_name"]

MAX_TOOL_NAME_CHARS = MAX_PROVIDER_TOOL_NAME_CHARS


def fusion_tool_name(server: str, tool: str) -> str | None:
    """`mcp__<sunucu>__<araç>`; tam adı 128 karakteri aşan araçta None."""
    return provider_mcp_tool_name(server, tool)

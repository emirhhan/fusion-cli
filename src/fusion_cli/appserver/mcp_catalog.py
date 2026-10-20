"""MCP araç tanımlarının çalıştırma yetkisi vermeyen insan görünümü."""

from __future__ import annotations

from typing import Any

from ..config.models import McpServerConfig
from ..core.redaction import contains_sensitive
from ..mcp_bridge.client import McpClient
from ..mcp_bridge.types import RemoteTool

_TYPES = frozenset({"string", "number", "integer", "boolean", "array", "object", "null"})


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    # Yalnız eşleşen parçayı değil tamamını gizle: kesilmiş JSON kuyruğu sızmasın.
    return "[Hassas açıklama gizlendi]" if contains_sensitive(value) else value[:limit]


def _parameters(schema: object) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(schema, dict) or not isinstance(schema.get("properties"), dict):
        return [], False
    properties = schema["properties"]
    required = schema.get("required", [])
    required = required if isinstance(required, list) else []
    result = []
    for name, raw in list(properties.items())[:40]:
        if not isinstance(name, str):
            continue
        definition = raw if isinstance(raw, dict) else {}
        kind = definition.get("type")
        result.append(
            {
                "name": _text(name, 120),
                "type": kind if isinstance(kind, str) and kind in _TYPES else "unknown",
                "required": name in required,
                "description": _text(definition.get("description"), 300),
            }
        )
    return result, len(properties) > 40


def project_tools(tools: list[RemoteTool]) -> dict[str, Any]:
    rows = []
    for tool in tools[:200]:
        parameters, truncated = _parameters(tool.schema)
        rows.append(
            {
                "name": _text(f"{tool.server}__{tool.name}", 240),
                "server": _text(tool.server, 120),
                "description": _text(tool.description, 600),
                "effect": tool.effect.value,
                "parameters": parameters,
                "parametersTruncated": truncated,
            }
        )
    return {"tools": rows, "total": len(tools), "truncated": len(tools) > 200}


async def list_tool_catalog(server: McpServerConfig) -> dict[str, Any]:
    """Açık katalog isteği: mevcut MCP yaşam döngüsüyle yalnız keşfet, giriş açma."""
    try:
        async with McpClient((server,), interactive=False) as client:
            status = client.statuses.get(server.name)
            if status is None or status.state != "bagli":
                return {
                    "ok": False,
                    "metin": "Araç kataloğu okunamadı. Bağlantı durumunu kontrol et.",
                }
            tools = await client.list_tools(server.name)
        return {"ok": True, "schemaVersion": 1, **project_tools(tools)}
    except Exception:
        # Sunucunun ham istisnası URL/token veya özel parametre taşıyabilir.
        return {"ok": False, "metin": "Araç kataloğu okunamadı. Bağlantıyı yeniden test et."}

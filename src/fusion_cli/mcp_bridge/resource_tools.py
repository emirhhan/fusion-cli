"""Modele MCP kaynaklarını listeleme ve okuma araçları (#255).

Claude Code: "Claude Code automatically provides tools to list and read MCP resources"
(`ListMcpResourcesTool`, `ReadMcpResourceTool`). İkisi de salt-okurdur; yalnız kaynak
yeteneği bildiren bağlı bir sunucu varken kaydedilir.
"""

from __future__ import annotations

from typing import Protocol

from ..core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from ..tools import ToolRegistry

LIST_TOOL = "ListMcpResourcesTool"
READ_TOOL = "ReadMcpResourceTool"


class _ResourceClient(Protocol):
    @property
    def servers(self) -> tuple[str, ...]: ...

    def has_resources(self, server: str) -> bool: ...

    async def catalog(self, server: str) -> object: ...

    async def read_resource(self, server: str, uri: str) -> str: ...


def register_resource_tools(client: _ResourceClient, registry: ToolRegistry) -> tuple[str, ...]:
    servers = tuple(server for server in client.servers if client.has_resources(server))
    if not servers:
        return ()

    async def _list(args: ToolArgs, context: ToolContext) -> ToolResult:
        del context
        wanted = str(args.get("server") or "").strip()
        lines: list[str] = []
        for server in servers:
            if wanted and server != wanted:
                continue
            catalog = await client.catalog(server)
            for item in getattr(catalog, "resources", ()):
                uri = getattr(item, "uri", "")
                if uri.startswith("ui://") or getattr(item, "mime_type", "").endswith("mcp-app"):
                    continue  # Claude Code ui:// ve mcp-app kaynaklarını listelemez
                name = getattr(item, "name", "") or uri
                lines.append(f"{server}\t{uri}\t{name}")
        return ToolResult(output="\n".join(lines) or "Kaynak yok.")

    async def _read(args: ToolArgs, context: ToolContext) -> ToolResult:
        del context
        server = str(args.get("server") or "").strip()
        uri = str(args.get("uri") or "").strip()
        if server not in servers or not uri:
            return ToolResult.failure(f"Geçerli sunucu ve uri gerekli. Sunucular: {', '.join(servers)}")
        return ToolResult(output=await client.read_resource(server, uri))

    registry.register_or_replace(
        Tool(
            name=LIST_TOOL,
            description="Bağlı MCP sunucularının kaynaklarını listeler (sunucu, uri, ad).",
            parameters={
                "type": "object",
                "properties": {"server": {"type": "string", "description": "İsteğe bağlı sunucu adı"}},
            },
            run=_list,
            effect=ToolEffect.REMOTE_READ,
        )
    )
    registry.register_or_replace(
        Tool(
            name=READ_TOOL,
            description="Bir MCP kaynağını sunucu adı ve uri ile okur.",
            parameters={
                "type": "object",
                "properties": {"server": {"type": "string"}, "uri": {"type": "string"}},
                "required": ["server", "uri"],
            },
            run=_read,
            effect=ToolEffect.REMOTE_READ,
        )
    )
    return (LIST_TOOL, READ_TOOL)

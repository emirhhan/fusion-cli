"""MCP SUNUCUSU — Fusion'ın araçlarını başka AI uygulamalarına açar.

`fusion mcp` çalıştırıldığında, Fusion'ın araçları (kod arama, dosya okuma, dizin
listeleme, glob…) resmî **Model Context Protocol** üzerinden bir prize konur. MCP
destekleyen her istemci (Claude masaüstü, Cursor, Cline…) bu prize takılıp Fusion'ın
araçlarını kullanabilir.

Güvenlik: VARSAYILAN olarak yalnızca DEĞİŞTİRMEYEN (salt-okunur) araçlar açılır —
dışarıdan gelen bir istemciye shell/dosya-yazma vermek risklidir. Değiştirici araçları
açmak `--write` ile bilinçli bir adımdır.

`mcp` paketi opsiyoneldir (`fusion-cli[mcp]`); yoksa `fusion mcp` anlaşılır hata verir.
"""

from __future__ import annotations

from pathlib import Path

import mcp.types as mcp_types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ..core.tools import ToolContext
from ..tools import build_registry


def build_server(root: Path, *, expose_mutating: bool = False) -> Server:
    """Fusion araçlarını sunan bir MCP `Server` kur (stdio ile çalıştırılır).

    `expose_mutating=False` (varsayılan) yalnızca salt-okunur araçları açar.
    """
    registry = build_registry()
    context = ToolContext(root=root)
    exposed = {
        name for name in registry.names() if expose_mutating or not _is_mutating(registry, name)
    }
    server: Server = Server("fusion")

    @server.list_tools()
    async def _list() -> list[mcp_types.Tool]:
        tools = []
        for name in registry.names():
            if name not in exposed:
                continue
            tool = registry.get(name)
            if tool is None:
                continue
            tools.append(
                mcp_types.Tool(
                    name=name,
                    description=tool.description,
                    inputSchema=dict(tool.parameters),
                )
            )
        return tools

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, object]) -> list[mcp_types.TextContent]:
        if name not in exposed:
            return [mcp_types.TextContent(type="text", text=f"Araç sunulmuyor: {name}")]
        result = await registry.execute(name, arguments or {}, context)
        return [mcp_types.TextContent(type="text", text=result.output)]

    return server


def _is_mutating(registry: object, name: str) -> bool:
    tool = registry.get(name)  # type: ignore[attr-defined]
    return bool(tool and tool.mutating)


async def run_stdio(root: Path, *, expose_mutating: bool = False) -> None:
    """MCP sunucusunu stdio üzerinden çalıştır (istemci süreci başlatır)."""
    server = build_server(root, expose_mutating=expose_mutating)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":  # `python -m fusion_cli.mcp_bridge.server <kök> [--write]`
    import asyncio
    import sys

    _root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    _write = "--write" in sys.argv[2:]
    asyncio.run(run_stdio(_root, expose_mutating=_write))

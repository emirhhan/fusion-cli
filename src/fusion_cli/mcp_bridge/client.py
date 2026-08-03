"""MCP İSTEMCİSİ — dışarıdaki MCP sunucularının araçlarını Fusion'a takar.

Dünyada yüzlerce hazır MCP sunucusu var (GitHub, veritabanı, tarayıcı…). Bu istemci
onlara bağlanır, araçlarını KEŞFEDER ve Fusion'ın araç kayıt defterine ekler; böylece
Fusion'ın ajanı bu dış araçları da kullanabilir.

Bağlantı stdio üzerinden kurulur (Claude masaüstü/Cursor'ın kullandığı yaygın biçim):
istemci, sunucu sürecini bir komutla başlatır. Oturumlar `AsyncExitStack` ile açık
tutulur ve kapanışta hep birlikte temizlenir.

Güvenlik: dış araçların ne yaptığını bilemeyiz; hepsi `mutating=True` kaydedilir —
yani Fusion'ın ONAY akışından geçerler (kullanıcı görmeden çalışmazlar).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..config.models import McpServerConfig
from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ..tools import ToolRegistry

__all__ = ["McpClient", "McpServerConfig", "RemoteTool"]

#: Uzak aracı Fusion'a bağlayan çalıştırıcı (async ToolExecutor).
_ToolRun = Callable[[ToolArgs, ToolContext], Awaitable[ToolResult]]


@dataclass(slots=True)
class RemoteTool:
    """Uzak bir MCP aracının Fusion'a taşınan tanımı."""

    server: str
    name: str
    description: str
    schema: dict[str, object] = field(default_factory=dict)


class McpClient:
    """Yapılandırılmış MCP sunucularına bağlanan, araçlarını taşıyan istemci."""

    def __init__(self, configs: Sequence[McpServerConfig]) -> None:
        self._configs = tuple(configs)
        self._stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}

    async def __aenter__(self) -> McpClient:
        for config in self._configs:
            params = StdioServerParameters(command=config.command, args=list(config.args))
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[config.name] = session
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    async def list_tools(self, server: str) -> list[RemoteTool]:
        """Bir sunucunun araçlarını keşfet."""
        result = await self._sessions[server].list_tools()
        return [
            RemoteTool(
                server=server,
                name=tool.name,
                description=tool.description or "",
                schema=dict(tool.inputSchema or {}),
            )
            for tool in result.tools
        ]

    async def call(self, server: str, name: str, args: dict[str, object]) -> str:
        """Uzak bir aracı çağır ve metin sonucunu döndür."""
        result = await self._sessions[server].call_tool(name, args)
        parts = [
            getattr(block, "text", "")
            for block in result.content
            if getattr(block, "type", None) == "text"
        ]
        return "".join(parts)

    async def register_into(self, registry: ToolRegistry) -> tuple[str, ...]:
        """Tüm sunucuların araçlarını Fusion kayıt defterine ekle; eklenen adları döndür.

        Ad çakışmasını önlemek için araçlar `<sunucu>__<araç>` biçiminde adlandırılır.
        """
        added: list[str] = []
        for server in self._sessions:
            for remote in await self.list_tools(server):
                fusion_name = f"{server}__{remote.name}"
                registry.register(
                    Tool(
                        name=fusion_name,
                        description=remote.description,
                        parameters=remote.schema,
                        run=self._make_run(server, remote.name),
                        # Dış araç ne yaptığını söylemez: onay akışına girsin diye mutating.
                        mutating=True,
                    )
                )
                added.append(fusion_name)
        return tuple(added)

    def _make_run(self, server: str, tool: str) -> _ToolRun:
        async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
            try:
                text = await self.call(server, tool, dict(args))
            except Exception as error:
                return ToolResult.failure(f"MCP aracı hatası ({server}.{tool}): {error}")
            return ToolResult(output=text)

        return _run

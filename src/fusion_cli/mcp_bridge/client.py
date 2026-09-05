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
from .content import normalize_call_result

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
        try:
            for config in self._configs:
                params = StdioServerParameters(command=config.command, args=list(config.args))
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[config.name] = session
        except Exception:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    async def list_tools(self, server: str) -> list[RemoteTool]:
        """Bir sunucunun araçlarını keşfet."""
        remote: list[RemoteTool] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            if cursor is None:
                result = await self._sessions[server].list_tools()
            else:
                result = await self._sessions[server].list_tools(cursor)
            remote.extend(
                RemoteTool(
                    server=server,
                    name=tool.name,
                    description=tool.description or "",
                    schema=dict(tool.inputSchema or {}),
                )
                for tool in result.tools
            )
            next_cursor = getattr(result, "nextCursor", None)
            if not next_cursor or next_cursor in seen:
                return remote
            seen.add(next_cursor)
            cursor = next_cursor

    async def call(self, server: str, name: str, args: dict[str, object]) -> ToolResult:
        """Uzak aracı çağır; bütün içeriği ve hata durumunu kanonik sonuca dönüştür.

        `isError` bayrağı ATILAMAZ. Eskiden yalnız metin dönüyordu ve uzak araç
        "Scene file does not exist" dediğinde Fusion bunu BAŞARI sayıyordu.
        Model düzeltemediği için aynı çağrıyı tekrarlıyor, tekrar koruması
        engelliyor ve tur yarım bitiyordu — kullanıcı boş bir hata mesajıyla
        "görev başarısız" görüyordu.
        """
        result = await self._sessions[server].call_tool(name, args)
        return normalize_call_result(result)

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
            del context
            try:
                result = await self.call(server, tool, dict(args))
            except Exception as error:
                return ToolResult.failure(f"MCP aracı hatası ({server}.{tool}): {error}")
            if not result.ok and not result.output:
                # Modele DÜZELTME şansı veren hata: metin olduğu gibi taşınır,
                # çünkü uzak sunucular genelde çözüm önerisini oraya yazar.
                return ToolResult.failure(
                    f"MCP aracı başarısız: {server}.{tool}",
                    content=result.content,
                    structured=result.structured,
                )
            return result

        return _run

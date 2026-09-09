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

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from mcp import ClientSession

from ..config.models import McpServerConfig
from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ..tools import ToolRegistry
from .content import normalize_call_result
from .transport import open_mcp_stream

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


@dataclass(frozen=True, slots=True)
class McpConnectionStatus:
    """Bir MCP sunucusunun diğerlerinden bağımsız sağlık sonucu."""

    server: str
    state: str
    tool_count: int = 0
    latency_ms: int = 0
    message: str | None = None


class McpClient:
    """Yapılandırılmış MCP sunucularına bağlanan, araçlarını taşıyan istemci."""

    def __init__(self, configs: Sequence[McpServerConfig], *, timeout_seconds: float = 10) -> None:
        self._configs = tuple(configs)
        self._timeout_seconds = timeout_seconds
        self._stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._statuses: dict[str, McpConnectionStatus] = {}

    @property
    def statuses(self) -> dict[str, McpConnectionStatus]:
        return dict(self._statuses)

    async def __aenter__(self) -> McpClient:
        for config in self._configs:
            await self._connect_server(config)
        return self

    async def __aexit__(self, *exc: object) -> None:
        for stack in reversed(tuple(self._stacks.values())):
            await stack.aclose()
        self._stacks.clear()
        self._sessions.clear()

    async def _connect_server(self, config: McpServerConfig) -> None:
        started = time.monotonic()
        stack = AsyncExitStack()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                read, write = await stack.enter_async_context(open_mcp_stream(config))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[config.name] = session
                self._stacks[config.name] = stack
                self._statuses[config.name] = McpConnectionStatus(
                    server=config.name,
                    state="bagli",
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
        except TimeoutError:
            await stack.aclose()
            self._statuses[config.name] = McpConnectionStatus(
                server=config.name,
                state="zaman_asimi",
                latency_ms=int((time.monotonic() - started) * 1000),
                message="MCP başlatma zaman aşımına uğradı.",
            )
        except Exception:
            await stack.aclose()
            self._statuses[config.name] = McpConnectionStatus(
                server=config.name,
                state="hata",
                latency_ms=int((time.monotonic() - started) * 1000),
                message="MCP sunucusu başlatılamadı.",
            )

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
            tools = await self.list_tools(server)
            current = self._statuses.get(server)
            if current is not None:
                self._statuses[server] = McpConnectionStatus(
                    server=server,
                    state=current.state,
                    tool_count=len(tools),
                    latency_ms=current.latency_ms,
                    message=current.message,
                )
            for remote in tools:
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

"""MCP İSTEMCİSİ — dışarıdaki MCP sunucularının araçlarını Fusion'a takar.

Dünyada yüzlerce hazır MCP sunucusu var (GitHub, veritabanı, tarayıcı…). Bu istemci
onlara bağlanır, araçlarını KEŞFEDER ve Fusion'ın araç kayıt defterine ekler; böylece
Fusion'ın ajanı bu dış araçları da kullanabilir.

Bağlantı stdio üzerinden kurulur (Claude masaüstü/Cursor'ın kullandığı yaygın biçim):
istemci, sunucu sürecini bir komutla başlatır. Oturumlar `AsyncExitStack` ile açık
tutulur ve kapanışta hep birlikte temizlenir.

Güvenlik: dış araçlar `mutating=True` kaydedilir, yani onay akışına girerler. Aracın
MCP açıklaması `effect` alanına çevrilir: auto kip uzak yazma araçlarını ilk
çağrıda, yıkıcı araçları her çağrıda sorar (bkz. `tool_effect.py`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from typing import TextIO, cast

from mcp import ClientSession

from ..config.models import McpServerConfig, McpTransport
from ..core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from ..tools import ToolRegistry
from .content import normalize_call_result
from .failures import STATE_CONNECTED, classify_failure
from .tool_effect import effect_from_annotations
from .transport import open_mcp_stream

__all__ = ["McpClient", "McpServerConfig", "RemoteTool"]

_LOG = logging.getLogger(__name__)

#: Uzak aracı Fusion'a bağlayan çalıştırıcı (async ToolExecutor).
_ToolRun = Callable[[ToolArgs, ToolContext], Awaitable[ToolResult]]

#: Stdio sunucusunun stderr'inden sınıflandırma için okunan en fazla bayt.
#: npm'in E404 bloğu ~600 bayttır; kuyruğun birkaç katı yeter, tüm dosya okunmaz.
_STDERR_TAIL_BYTES = 4096


@dataclass(slots=True)
class RemoteTool:
    """Uzak bir MCP aracının Fusion'a taşınan tanımı."""

    server: str
    name: str
    description: str
    schema: dict[str, object] = field(default_factory=dict)
    effect: ToolEffect = ToolEffect.REMOTE_WRITE


@dataclass(frozen=True, slots=True)
class McpConnectionStatus:
    """Bir MCP sunucusunun diğerlerinden bağımsız sağlık sonucu."""

    server: str
    state: str
    tool_count: int = 0
    latency_ms: int = 0
    message: str | None = None
    #: Başarısızlık türü (`failures.McpFailureKind` değeri); başarıda None.
    kind: str | None = None


async def _close_failed_stack(stack: AsyncExitStack, error: BaseException) -> BaseException | None:
    """Başarısız bağlantının kaynaklarını kapat; asıl hatayı döndür, dış iptalde None.

    SDK taşıma görev grubundaki hatayı (ör. OAuth kaydı reddi) bekleyen
    `initialize` çağrısını İPTAL ederek bildirir; asıl hata ancak görev grubu
    kapanırken `ExceptionGroup` içinde görünür. Ölçüldü (Meta Ads MCP): bu iptal
    `except Exception`'dan kaçıyor, giriş görevini düşürüyor ve arayüz sonsuza
    dek "Giriş bekleniyor" gösteriyordu. Görevin kendisi dışarıdan iptal
    edildiyse iptal yutulmaz.
    """
    try:
        await stack.aclose()
    except Exception as close_error:  # görev grubu asıl hatayı kapanışta verir
        error = close_error
    if isinstance(error, Exception):
        return error
    task = asyncio.current_task()
    is_internal_cancel = isinstance(error, asyncio.CancelledError) and (
        task is None or task.cancelling() == 0
    )
    return error if is_internal_cancel else None


def _read_tail(capture: TextIO) -> str:
    """Geçici stderr dosyasının son kısmını oku (bloklayan; thread'de çağrılır)."""
    capture.flush()
    size = capture.seek(0, os.SEEK_END)
    capture.seek(max(0, size - _STDERR_TAIL_BYTES))
    return capture.read()


def failure_status(
    config: McpServerConfig, error: BaseException, *, latency_ms: int, stderr_tail: str = ""
) -> McpConnectionStatus:
    """Başarısızlığı kullanıcının üzerine eylem yapabileceği duruma çevir."""
    failure = classify_failure(error, config, stderr_tail=stderr_tail)
    return McpConnectionStatus(
        server=config.name,
        state=failure.state,
        latency_ms=latency_ms,
        message=failure.message,
        kind=failure.kind.value,
    )


class McpClient:
    """Yapılandırılmış MCP sunucularına bağlanan, araçlarını taşıyan istemci."""

    def __init__(
        self,
        configs: Sequence[McpServerConfig],
        *,
        timeout_seconds: float = 10,
        interactive: bool = True,
    ) -> None:
        self._configs = tuple(configs)
        self._timeout_seconds = timeout_seconds
        #: Giriş penceresi açılabilir mi? Tur yolu bunu KAPATIR.
        self._interactive = interactive
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
        stderr_capture: TextIO | None = None
        try:
            if config.transport is McpTransport.STDIO:
                # Sunucunun stderr'i geçici dosyaya: paket bulunamadığında asıl
                # neden yalnız orada görünür. Dosya bağlantıyla birlikte kapanır
                # ve silinir.
                # `TemporaryFile` metin kipinde TextIO döner; stub genel `IO[str]` der.
                stderr_capture = cast(
                    TextIO,
                    await asyncio.to_thread(
                        tempfile.TemporaryFile, "w+", encoding="utf-8", errors="replace"
                    ),
                )
                stack.callback(stderr_capture.close)
            async with asyncio.timeout(self._timeout_seconds) as deadline:
                auth = None
                # Token yolu OAuth'u tamamen atlar: istek başlığı yeter, giriş
                # penceresi açılmaz ve her turda yeniden yetkilendirme denenmez.
                if config.transport is McpTransport.STREAMABLE_HTTP and not config.token_env:
                    from .oauth import oauth_provider_for

                    bundle = await oauth_provider_for(
                        config,
                        on_waiting=self._deadline_pause(deadline),
                        interactive=self._interactive,
                    )
                    auth = bundle.auth
                    stack.push_async_callback(bundle.callback.close)
                read, write = await stack.enter_async_context(
                    open_mcp_stream(config, auth=auth, errlog=stderr_capture)
                )
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[config.name] = session
                self._stacks[config.name] = stack
                self._statuses[config.name] = McpConnectionStatus(
                    server=config.name,
                    state=STATE_CONNECTED,
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
        except BaseException as error:
            stderr_tail = ""
            if stderr_capture is not None and not stderr_capture.closed:
                stderr_tail = await asyncio.to_thread(_read_tail, stderr_capture)
            failure = await _close_failed_stack(stack, error)
            if failure is None:
                raise
            status = failure_status(
                config,
                failure,
                latency_ms=int((time.monotonic() - started) * 1000),
                stderr_tail=stderr_tail,
            )
            # Sunucu çıktısı LOG'A YAZILMAZ: sır (bağlantı adresi, token) taşıyabilir.
            _LOG.warning(
                "MCP bağlantısı kurulamadı",
                extra={"sunucu": config.name, "hata": type(failure).__name__, "tur": status.kind},
            )
            self._statuses[config.name] = status

    def _deadline_pause(self, deadline: asyncio.Timeout) -> Callable[[bool], None]:
        """Kullanıcı tarayıcıda giriş yaparken bağlantı süresini durdur.

        Süre ağ adımları içindir; OAuth girişini bekleyen kullanıcıya uygulanınca
        girişi saniyeler içinde bitirmeyen herkes "zaman aşımı" görüyordu. Bekleme
        kendi üst sınırını `LoopbackOAuthCallback` içinde taşır.
        """
        loop = asyncio.get_running_loop()

        def on_waiting(is_waiting: bool) -> None:
            # Bağlam kapandıktan sonra gelen bildirim (iptal temizliği) anlamsızdır.
            with contextlib.suppress(RuntimeError):
                deadline.reschedule(None if is_waiting else loop.time() + self._timeout_seconds)

        return on_waiting

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
                    # Sahte ve eski SDK araç nesnelerinde alan olmayabilir.
                    effect=effect_from_annotations(getattr(tool, "annotations", None)),
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
                self._statuses[server] = replace(current, tool_count=len(tools))
            for remote in tools:
                fusion_name = f"{server}__{remote.name}"
                # Üzerine yazılır: bağlantı oturum boyunca yaşıyor ve aynı defter
                # ikinci turda yeniden beslenebilir (bkz. `mcp_bridge/pool.py`).
                registry.register_or_replace(
                    Tool(
                        name=fusion_name,
                        description=remote.description,
                        parameters=remote.schema,
                        run=self._make_run(server, remote.name),
                        # Dış araç ne yaptığını söylemez: onay akışına girsin diye mutating.
                        mutating=True,
                        effect=remote.effect,
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

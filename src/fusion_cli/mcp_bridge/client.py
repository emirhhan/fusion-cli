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
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import replace
from typing import Literal, TextIO, cast

from mcp import ClientSession

from ..config.models import McpServerConfig, McpTransport
from ..core.constants import MCP_NETWORK_TIMEOUT_S
from ..core.tools import EffectResolver, Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from ..tools import ToolRegistry
from .ability_effects import ABILITY_INFO, EXECUTE_ABILITY, ability_gateway_resolver
from .cancellation import RequestTracker, notify_cancel
from .content import normalize_call_result
from .failures import STATE_CONNECTED
from .health import failure_status as failure_status
from .lifecycle import close_failed_stack
from .tool_effect import effect_from_annotations
from .transport import open_mcp_stream
from .trust import trusted_effect
from .types import McpConnectionStatus as McpConnectionStatus
from .types import RemoteTool as RemoteTool

__all__ = ["McpClient", "McpServerConfig", "RemoteTool"]

_LOG = logging.getLogger(__name__)

#: Uzak aracı Fusion'a bağlayan çalıştırıcı (async ToolExecutor).
_ToolRun = Callable[[ToolArgs, ToolContext], Awaitable[ToolResult]]

#: Stdio sunucusunun stderr'inden sınıflandırma için okunan en fazla bayt.
#: npm'in E404 bloğu ~600 bayttır; kuyruğun birkaç katı yeter, tüm dosya okunmaz.
_STDERR_TAIL_BYTES = 4096


class McpNotConnectedError(RuntimeError):
    """İstenen MCP sunucusuna bağlantı yok: araç listelenemez, çağrılamaz.

    Eskiden bu durumda oturum sözlüğü ham `KeyError` fırlatıyordu; kullanıcı
    sunucu adından ibaret, hiçbir şey anlatmayan bir hata görüyordu. Bağlantı
    neden kurulamadıysa (`_statuses`) mesaj onu söyler — sınıflandırılmış
    bağlantı hatası zaten orada duruyor.
    """


def _read_tail(capture: TextIO) -> str:
    """Geçici stderr dosyasının son kısmını oku (bloklayan; thread'de çağrılır)."""
    capture.flush()
    size = capture.seek(0, os.SEEK_END)
    capture.seek(max(0, size - _STDERR_TAIL_BYTES))
    return capture.read()


class McpClient:
    """Yapılandırılmış MCP sunucularına bağlanan, araçlarını taşıyan istemci."""

    def __init__(
        self,
        configs: Sequence[McpServerConfig],
        *,
        timeout_seconds: float = MCP_NETWORK_TIMEOUT_S,
        interactive: bool = True,
    ) -> None:
        self._configs = tuple(configs)
        self._tracker = RequestTracker()
        self._timeout_seconds = timeout_seconds
        #: Giriş penceresi açılabilir mi? Tur yolu bunu KAPATIR.
        self._interactive = interactive
        self._stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._statuses: dict[str, McpConnectionStatus] = {}

    def _trusted_effect(self, server: str, effect: ToolEffect | None) -> ToolEffect | None:
        """Statik ve dinamik araç iddiaları aynı kaynak güven kapısından geçer."""
        config = next((config for config in self._configs if config.name == server), None)
        if config is None:
            return ToolEffect.REMOTE_WRITE if effect is ToolEffect.REMOTE_READ else effect
        return trusted_effect(config, effect)

    def _server_timeout(
        self, server: str, budget: Literal["list_timeout_s", "call_timeout_s", "close_timeout_s"]
    ) -> float:
        """Sunucu bütçesi yoksa kayıtlı oturumun mevcut istemci sınırını koru."""
        config = next((config for config in self._configs if config.name == server), None)
        configured = cast(float | None, getattr(config, budget, None))
        return self._timeout(configured)

    def _timeout(self, configured: float | None) -> float:
        """Ayrı değer yoksa mevcut constructor bütçesini koru."""
        return configured if configured is not None else self._timeout_seconds

    @property
    def statuses(self) -> dict[str, McpConnectionStatus]:
        return dict(self._statuses)

    async def __aenter__(self) -> McpClient:
        for config in self._configs:
            await self._connect_server(config)
        return self

    async def __aexit__(self, *exc: object) -> None:
        try:
            for server, stack in reversed(tuple(self._stacks.items())):
                try:
                    # AnyIO kapsamı açan görev kendi stack'ini kapatır.
                    async with asyncio.timeout(self._server_timeout(server, "close_timeout_s")):
                        await stack.aclose()
                except Exception as error:
                    config = next(
                        (item for item in self._configs if item.name == server),
                        McpServerConfig(server),
                    )
                    self._statuses[server] = failure_status(config, error, latency_ms=0)
                    _LOG.warning(
                        "MCP kapanışı başarısız",
                        extra={"sunucu": server, "hata": type(error).__name__},
                    )
        finally:
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
            async with asyncio.timeout(self._timeout(config.connect_timeout_s)) as deadline:
                auth = None
                # Token yolu OAuth'u tamamen atlar: istek başlığı yeter, giriş
                # penceresi açılmaz ve her turda yeniden yetkilendirme denenmez.
                if config.transport is McpTransport.STREAMABLE_HTTP and not config.token_env:
                    from .oauth import oauth_provider_for

                    bundle = await oauth_provider_for(
                        config,
                        on_waiting=self._deadline_pause(
                            deadline, self._timeout(config.connect_timeout_s)
                        ),
                        interactive=self._interactive,
                    )
                    auth = bundle.auth
                    stack.push_async_callback(bundle.callback.close)
                read, write = await stack.enter_async_context(
                    open_mcp_stream(config, auth=auth, errlog=stderr_capture)
                )
                session = await stack.enter_async_context(
                    ClientSession(read, self._tracker.wrap(config.name, write))
                )
                await session.initialize()
                self._sessions[config.name] = session
                self._stacks[config.name] = stack
                self._statuses[config.name] = McpConnectionStatus(
                    server=config.name,
                    state=STATE_CONNECTED,
                    observed_at=time.monotonic(),
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
        except BaseException as error:
            stderr_tail = ""
            if stderr_capture is not None and not stderr_capture.closed:
                stderr_tail = await asyncio.to_thread(_read_tail, stderr_capture)
            failure = await close_failed_stack(stack, error, self._timeout(config.close_timeout_s))
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

    def _deadline_pause(
        self, deadline: asyncio.Timeout, timeout_seconds: float
    ) -> Callable[[bool], None]:
        """Kullanıcı tarayıcıda giriş yaparken bağlantı süresini durdur.

        Süre ağ adımları içindir; OAuth girişini bekleyen kullanıcıya uygulanınca
        girişi saniyeler içinde bitirmeyen herkes "zaman aşımı" görüyordu. Bekleme
        kendi üst sınırını `LoopbackOAuthCallback` içinde taşır.
        """
        loop = asyncio.get_running_loop()

        def on_waiting(is_waiting: bool) -> None:
            # Bağlam kapandıktan sonra gelen bildirim (iptal temizliği) anlamsızdır.
            with contextlib.suppress(RuntimeError):
                deadline.reschedule(None if is_waiting else loop.time() + timeout_seconds)

        return on_waiting

    def _session(self, server: str) -> ClientSession:
        """Bağlı oturumu getir; yoksa nedenini söyleyen hata fırlat."""
        session = self._sessions.get(server)
        if session is not None:
            return session
        if not any(config.name == server for config in self._configs):
            raise McpNotConnectedError(f"MCP sunucusu tanımlı değil: {server}.")
        durum = self._statuses.get(server)
        neden = durum.message if durum is not None and durum.message else ""
        raise McpNotConnectedError(
            f"MCP sunucusuna bağlantı yok: {server}."
            + (f" {neden}" if neden else " Bağlantıyı kontrol edip yeniden dene.")
        )

    async def list_tools(self, server: str) -> list[RemoteTool]:
        """Bütün keşif sayfalarını tek ağ bütçesiyle sınırla."""
        async with asyncio.timeout(self._server_timeout(server, "list_timeout_s")):
            return await self._list_tools(server)

    async def _list_tools(self, server: str) -> list[RemoteTool]:
        """Bir sunucunun araçlarını keşfet."""
        remote: list[RemoteTool] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            if cursor is None:
                result = await self._session(server).list_tools()
            else:
                result = await self._session(server).list_tools(cursor)
            remote.extend(
                RemoteTool(
                    server=server,
                    name=tool.name,
                    description=tool.description or "",
                    schema=dict(tool.inputSchema or {}),
                    # Sahte ve eski SDK araç nesnelerinde alan olmayabilir.
                    effect=self._trusted_effect(
                        server, effect_from_annotations(getattr(tool, "annotations", None))
                    )
                    or ToolEffect.REMOTE_WRITE,
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
        session = self._session(server)
        with self._tracker.track(server) as scope:
            try:
                async with asyncio.timeout(self._server_timeout(server, "call_timeout_s")):
                    result = await session.call_tool(name, args)
                    normalized = normalize_call_result(result)
                    current = self._statuses.get(server)
                    if current is not None:
                        self._statuses[server] = replace(
                            current,
                            state=STATE_CONNECTED,
                            message=None,
                            kind=None,
                            observed_at=time.monotonic(),
                        )
                    return normalized
            except (asyncio.CancelledError, TimeoutError):
                self._statuses[server] = McpConnectionStatus(
                    server,
                    "degraded",
                    message="Çağrı durduruldu; uzak sonucu gözlemeden tekrarlama.",
                    observed_at=time.monotonic(),
                )
                await notify_cancel(session, scope, self._server_timeout(server, "close_timeout_s"))
                raise

    async def register_into(self, registry: ToolRegistry) -> tuple[str, ...]:
        """Tüm sunucuların araçlarını Fusion kayıt defterine ekle; eklenen adları döndür.

        Ad çakışmasını önlemek için araçlar `<sunucu>__<araç>` biçiminde adlandırılır.
        """
        added: list[str] = []
        for server in self._sessions:
            try:
                tools = await self.list_tools(server)
            except Exception as error:
                config = next(config for config in self._configs if config.name == server)
                self._statuses[server] = failure_status(config, error, latency_ms=0)
                _LOG.warning(
                    "MCP araçları keşfedilemedi",
                    extra={"sunucu": server, "hata": type(error).__name__},
                )
                continue
            current = self._statuses.get(server)
            if current is not None:
                self._statuses[server] = replace(current, tool_count=len(tools))
            resolver = self._ability_resolver(server, {remote.name for remote in tools})
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
                        effect_resolver=resolver if remote.name == EXECUTE_ABILITY else None,
                    )
                )
                added.append(fusion_name)
        return tuple(added)

    def _ability_resolver(self, server: str, names: set[str]) -> EffectResolver | None:
        """WordPress `mcp-adapter` geçidi varsa yetenek bazlı etki çözücüsü kur."""
        if not {EXECUTE_ABILITY, ABILITY_INFO} <= names:
            return None

        async def info(ability: str) -> Mapping[str, object] | None:
            result = await self.call(server, ABILITY_INFO, {"ability_name": ability})
            return result.structured if result.ok else None

        resolver = ability_gateway_resolver(info)

        async def resolve(args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
            return self._trusted_effect(server, await resolver(args, context))

        return resolve

    def _make_run(self, server: str, tool: str) -> _ToolRun:
        async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
            del context
            try:
                result = await self.call(server, tool, dict(args))
            except TimeoutError:
                return ToolResult.failure(
                    f"MCP çağrısı süre sınırını aştı ({server}.{tool}). "
                    "Uzak işlemin sonucu belirsiz; tekrarlamadan önce durumu gözle."
                )
            except Exception as error:
                _LOG.warning(
                    "MCP aracı başarısız", extra={"sunucu": server, "hata": type(error).__name__}
                )
                return ToolResult.failure(
                    f"MCP aracı hatası ({server}.{tool}): {type(error).__name__}"
                )
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

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
import functools
import logging
import os
import tempfile
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import replace
from typing import Any, Literal, TextIO, cast

from mcp import ClientSession
from mcp.client.session import ClientSession as _SdkSession
from mcp.types import CallToolResult

from ..config.models import McpServerConfig, McpTransport
from ..core.constants import MCP_NETWORK_TIMEOUT_S
from ..core.tools import EffectResolver, Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from ..tools import ToolRegistry
from .ability_effects import ABILITY_INFO, EXECUTE_ABILITY, ability_gateway_resolver
from .auth_retry import AuthFailures, Reauth
from .call_errors import describe_call_error
from .cancellation import RequestTracker, notify_cancel
from .content import normalize_call_result
from .elicitation import elicitation_callback
from .failures import STATE_CONNECTED, STATE_LOGIN_REQUIRED
from .headers_helper import has_authorization, run_headers_helper
from .health import failure_status as failure_status
from .lifecycle import close_failed_stack
from .output_limits import declared_limit
from .references import (
    McpCatalog,
    as_uri,
    catalog_change_handler,
    fetch_catalog,
    prompt_text,
    resource_block,
)
from .resource_tools import register_resource_tools
from .schema import clean_description, simplify_schema
from .timeouts import idle_timeout_s, startup_timeout_s, tool_timeout_s
from .tool_effect import effect_from_annotations
from .tool_limits import select_remote_tools
from .tool_name import fusion_tool_name
from .transport import open_mcp_stream
from .trust import tools_digest, trusted_effect
from .types import McpConnectionStatus as McpConnectionStatus
from .types import RemoteTool as RemoteTool

__all__ = ["McpClient", "McpServerConfig", "RemoteTool"]

_LOG = logging.getLogger(__name__)

#: Uzak aracı Fusion'a bağlayan çalıştırıcı (async ToolExecutor).
_ToolRun = Callable[[ToolArgs, ToolContext], Awaitable[ToolResult]]

#: Stdio sunucusunun stderr'inden sınıflandırma için okunan en fazla bayt.
#: npm'in E404 bloğu ~600 bayttır; kuyruğun birkaç katı yeter, tüm dosya okunmaz.
_STDERR_TAIL_BYTES = 4096

#: Art arda bu kadar çağrı zaman aşımına uğrarsa oturum "takılı" sayılır ve havuz
#: bir sonraki turda yeniden bağlanır (bkz. `McpClient.is_stalled`).
STALLED_AFTER_TIMEOUTS = 3


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


async def _call_with_idle(
    session: ClientSession, name: str, args: dict[str, object], idle: float | None
) -> CallToolResult:
    """`tools/call`; yanıt ya da ilerleme bildirimi `idle` sn gelmezse TimeoutError."""
    async with asyncio.timeout(idle) as idle_scope:
        if idle is None or not isinstance(session, _SdkSession):
            return await session.call_tool(name, args)
        loop = asyncio.get_running_loop()

        async def _progress(progress: float, total: float | None, message: str | None) -> None:
            idle_scope.reschedule(loop.time() + idle)

        return await session.call_tool(name, args, progress_callback=_progress)


class McpClient:
    """Yapılandırılmış MCP sunucularına bağlanan, araçlarını taşıyan istemci."""

    def __init__(
        self,
        configs: Sequence[McpServerConfig],
        *,
        timeout_seconds: float | None = None,
        interactive: bool = True,
    ) -> None:
        self._configs = tuple(configs)
        self._tracker = RequestTracker()
        #: Açıkça verilen bütçe eski davranışı korur (her aşama aynı sınır). Verilmezse
        #: Claude Code sınırları (`timeouts.py`): başlatma 30 sn, araç ~28 sa, boşta 5/30 dk.
        self._explicit_timeout = timeout_seconds
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else MCP_NETWORK_TIMEOUT_S
        )
        #: Giriş penceresi açılabilir mi? Tur yolu bunu KAPATIR.
        self._interactive = interactive
        self._stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._statuses: dict[str, McpConnectionStatus] = {}
        #: Sunucu başına ARDIŞIK çağrı zaman aşımı sayısı; başarı sıfırlar.
        self._timeouts: dict[str, int] = {}
        #: Sunucu başına son keşfedilen araç tanımı özeti; güven kaydıyla karşılaştırılır (M1-16).
        self._tool_digests: dict[str, str] = {}
        #: `prompts|resources/list_changed` bildiren sunucular: katalog yeniden çekilir (P-049).
        self._stale_catalogs: set[str] = set()
        #: `initialize` yanıtındaki sunucu talimatları (sınırlı, temizlenmiş).
        self._instructions: dict[str, str] = {}
        #: `tools/list_changed` bildiren sunucular: araç listesi yeniden çekilir (#256).
        self._stale_tools: set[str] = set()
        #: Sunucu başına deftere yazılan araç adları (kaldırılanları silmek için).
        self._registered: dict[str, set[str]] = {}
        #: Gözlenen 401/403 ve havuzun yeniden bağlanma geri çağırımı (#249).
        self._auth_failures = AuthFailures()
        self.reauth: Reauth | None = None
        self._successor: McpClient | None = None
        #: Araç başına `_meta["anthropic/maxResultSizeChars"]` sınırı (#240).
        self._result_limits: dict[tuple[str, str], int] = {}

    @property
    def is_stalled(self) -> bool:
        """Bir sunucu art arda zaman aşımına uğradı mı? Takılı süreç yeni çağrıları da
        düşürür; havuz bu istemciyi bırakıp yeniden bağlanmalı (ölçüldü 30 Ekim)."""
        return any(count >= STALLED_AFTER_TIMEOUTS for count in self._timeouts.values())

    def has_resources(self, server: str) -> bool:
        """Sunucu `resources` yeteneği bildirdi mi?"""
        session = self._sessions.get(server)
        getter = getattr(session, "get_server_capabilities", None)
        capabilities = getter() if callable(getter) else None
        return capabilities is not None and getattr(capabilities, "resources", None) is not None

    def server_instructions(self, server: str) -> str:
        """Sunucunun `initialize` talimatı; yoksa boş."""
        return self._instructions.get(server, "")

    def tools_stale(self, server: str) -> bool:
        """Sunucu son keşiften sonra `tools/list_changed` bildirdi mi?"""
        return server in self._stale_tools

    def registered_tool_names(self, server: str) -> tuple[str, ...]:
        """Sunucunun deftere yazılan araç adları (`/mcp tools`, #250)."""
        return tuple(sorted(self._registered.get(server, ())))

    def tool_digest(self, server: str) -> str:
        """Sunucudan en son keşfedilen araç tanımı özeti; keşif yoksa boş."""
        return self._tool_digests.get(server, "")

    def _trusted_effect(self, server: str, effect: ToolEffect | None) -> ToolEffect | None:
        """Statik ve dinamik araç iddiaları aynı kaynak güven kapısından geçer."""
        config = next((config for config in self._configs if config.name == server), None)
        if config is None:
            return ToolEffect.REMOTE_WRITE if effect is ToolEffect.REMOTE_READ else effect
        return trusted_effect(config, effect, self._tool_digests.get(server))

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

    def _config(self, server: str) -> McpServerConfig:
        return next(
            (config for config in self._configs if config.name == server), McpServerConfig(server)
        )

    def _connect_budget(self, config: McpServerConfig) -> float:
        if config.connect_timeout_s is None and self._explicit_timeout is not None:
            return self._explicit_timeout
        return startup_timeout_s(config)

    def _call_budgets(self, server: str) -> tuple[float, float | None]:
        """(duvar saati, boşta kalma) — araç çağrısı sınırları (#233)."""
        config = self._config(server)
        if config.call_timeout_s is None and self._explicit_timeout is not None:
            return self._explicit_timeout, None
        return tool_timeout_s(config), idle_timeout_s(config)

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
            async with asyncio.timeout(self._connect_budget(config)) as deadline:
                auth = None
                helper_headers = await run_headers_helper(config) if config.is_remote else {}
                # Token/Authorization yolu OAuth'u tamamen atlar: istek başlığı yeter, giriş
                # penceresi açılmaz ve her turda yeniden yetkilendirme denenmez (Claude Code:
                # headersHelper Authorization verirse OAuth'a düşülmez).
                if (
                    config.transport in (McpTransport.STREAMABLE_HTTP, McpTransport.SSE)
                    and not config.token_env
                    and not has_authorization({**dict(config.headers), **helper_headers})
                ):
                    from .oauth import oauth_provider_for

                    bundle = await oauth_provider_for(
                        config,
                        on_waiting=self._deadline_pause(deadline, self._connect_budget(config)),
                        interactive=self._interactive,
                    )
                    auth = bundle.auth
                    stack.push_async_callback(bundle.callback.close)
                read, write = await stack.enter_async_context(
                    open_mcp_stream(
                        config,
                        auth=auth,
                        errlog=stderr_capture,
                        extra_headers=helper_headers,
                        on_status=self._auth_failures.observer(config.name),
                    )
                )
                session = await stack.enter_async_context(
                    ClientSession(
                        read,
                        self._tracker.wrap(config.name, write),
                        message_handler=catalog_change_handler(
                            functools.partial(self._stale_catalogs.add, config.name),
                            functools.partial(self._stale_tools.add, config.name),
                        ),
                        # Claude Code elicitation: form ve url kipleri (#257).
                        elicitation_callback=elicitation_callback(config.name),
                    )
                )
                initialized = await session.initialize()
                # Claude Code sunucu talimatlarını oturum başında modele verir (#263).
                self._instructions[config.name] = clean_description(
                    str(getattr(initialized, "instructions", None) or "")
                )
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
        discovered: list[Any] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            if cursor is None:
                result = await self._session(server).list_tools()
            else:
                result = await self._session(server).list_tools(cursor)
            discovered.extend(result.tools)
            next_cursor = getattr(result, "nextCursor", None)
            if not next_cursor or next_cursor in seen:
                break
            seen.add(next_cursor)
            cursor = next_cursor
        for tool in discovered:
            limit = declared_limit(getattr(tool, "meta", None))
            if limit is not None:
                self._result_limits[(server, tool.name)] = limit
        # Özet, etkiler hesaplanmadan ÖNCE kaydedilir: değişen tanım okuma muafiyeti alamaz.
        digest = self._tool_digests[server] = tools_digest(discovered)
        config = next((item for item in self._configs if item.name == server), None)
        if config is not None and config.reviewed_tools and digest != config.reviewed_tools:
            _LOG.warning(
                "MCP araç tanımları incelemeden sonra değişti; güven düştü",
                extra={"sunucu": server},
            )
        remote_tools = [
            RemoteTool(
                server=server,
                name=tool.name,
                # Sağlayıcıya giden kopya sadeleşir/temizlenir (bkz. `schema.py`).
                description=clean_description(tool.description or ""),
                schema=simplify_schema(tool.inputSchema or {}),
                # Sahte ve eski SDK araç nesnelerinde alan olmayabilir.
                effect=self._trusted_effect(
                    server, effect_from_annotations(getattr(tool, "annotations", None))
                )
                or ToolEffect.REMOTE_WRITE,
            )
            for tool in discovered
        ]
        return select_remote_tools(config, remote_tools)

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
                wall, idle = self._call_budgets(server)
                async with asyncio.timeout(wall):
                    result = await _call_with_idle(session, name, args, idle)
                    normalized = normalize_call_result(
                        result, declared_chars=self._result_limits.get((server, name))
                    )
                    self._timeouts.pop(server, None)
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
            except (asyncio.CancelledError, TimeoutError) as error:
                if isinstance(error, TimeoutError):
                    self._timeouts[server] = self._timeouts.get(server, 0) + 1
                self._statuses[server] = McpConnectionStatus(
                    server,
                    "degraded",
                    message="Çağrı durduruldu; uzak sonucu gözlemeden tekrarlama.",
                    observed_at=time.monotonic(),
                )
                await notify_cancel(session, scope, self._server_timeout(server, "close_timeout_s"))
                raise

    # --- İstemler ve kaynaklar (P-049; bkz. `references.py`) ----------------------- #

    @property
    def servers(self) -> tuple[str, ...]:
        """Bağlı sunucu adları."""
        return tuple(self._sessions)

    def catalog_stale(self, server: str) -> bool:
        """Sunucu son çekimden sonra liste değişikliği bildirdi mi?"""
        return server in self._stale_catalogs

    async def catalog(self, server: str) -> McpCatalog:
        """Sunucunun istem ve kaynak listesi (keşif bütçesiyle sınırlı)."""
        self._stale_catalogs.discard(server)
        async with asyncio.timeout(self._server_timeout(server, "list_timeout_s")):
            return await fetch_catalog(self._session(server), server)

    async def get_prompt(self, server: str, name: str, arguments: dict[str, str]) -> str:
        """`prompts/get` → görev metni."""
        async with asyncio.timeout(self._server_timeout(server, "call_timeout_s")):
            result = await self._session(server).get_prompt(name, arguments or None)
        return prompt_text(result)

    async def read_resource(self, server: str, uri: str) -> str:
        """`resources/read` → maskeli, sınırlı bağlam bloğu."""
        async with asyncio.timeout(self._server_timeout(server, "call_timeout_s")):
            result = await self._session(server).read_resource(as_uri(uri))
        return resource_block(server, uri, result)

    async def register_into(self, registry: ToolRegistry) -> tuple[str, ...]:
        """Tüm sunucuların araçlarını Fusion kayıt defterine ekle; eklenen adları döndür.

        Araçlar Claude Code gibi `mcp__<sunucu>__<araç>` adını alır (#242); tam adı 128
        karakteri aşan araç kaydedilmez ve günlüğe yazılır.
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
                self._statuses[server] = replace(
                    current,
                    tool_count=len(tools),
                    tools_digest=self._tool_digests.get(server, ""),
                )
            resolver = self._ability_resolver(server, {remote.name for remote in tools})
            named = _named_tools(server, tools)
            current_names = {name for name, _remote in named}
            # `tools/list_changed` (#256): sunucunun kaldırdığı araçlar defterden de çıkar;
            # başarısız yenilemede (yukarıdaki `continue`) önceki araçlar korunur.
            for stale in self._registered.get(server, set()) - current_names:
                registry.unregister_remote(stale)
            self._registered[server] = current_names
            self._stale_tools.discard(server)
            for fusion_name, remote in named:
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
        added.extend(register_resource_tools(self, registry))
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

    def _current(self) -> McpClient:
        """Yeniden kimlik doğrulamayla yenilenen istemci zincirinin sonu (#249)."""
        client = self
        while client._successor is not None:
            client = client._successor
        return client

    async def _retry_after_auth(
        self, server: str, tool: str, args: dict[str, object]
    ) -> ToolResult | None:
        """401/403 + headersHelper: yardımcıyı yeniden çalıştırıp yeniden bağlan, bir kez dene."""
        config = next((item for item in self._configs if item.name == server), None)
        if config is None or not config.headers_helper or self.reauth is None:
            return None
        if not self._auth_failures.take(server):
            return None
        fresh = await self.reauth(server)
        if fresh is None or fresh is self:
            return None
        self._successor = fresh
        try:
            return await fresh.call(server, tool, args)
        except Exception as error:
            fresh._statuses[server] = McpConnectionStatus(
                server, STATE_LOGIN_REQUIRED, message=describe_call_error(error)
            )
            return ToolResult.failure(
                f"MCP aracı hatası ({server}.{tool}): {describe_call_error(error)}"
            )

    def _make_run(self, server: str, tool: str) -> _ToolRun:
        async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
            del context
            owner = self._current()
            try:
                result = await owner.call(server, tool, dict(args))
            except TimeoutError:
                return ToolResult.failure(
                    f"MCP çağrısı süre sınırını aştı ({server}.{tool}). "
                    "Uzak işlemin sonucu belirsiz; tekrarlamadan önce durumu gözle."
                )
            except Exception as error:
                _LOG.warning(
                    "MCP aracı başarısız", extra={"sunucu": server, "hata": type(error).__name__}
                )
                retried = await owner._retry_after_auth(server, tool, dict(args))
                if retried is not None:
                    return retried
                return ToolResult.failure(
                    f"MCP aracı hatası ({server}.{tool}): {describe_call_error(error)}"
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


def _named_tools(server: str, tools: Sequence[RemoteTool]) -> list[tuple[str, RemoteTool]]:
    """(kayıt adı, araç); Claude gibi tam adı 128 karakteri aşan araç dışarıda kalır."""
    named: list[tuple[str, RemoteTool]] = []
    for remote in tools:
        name = fusion_tool_name(server, remote.name)
        if name is None:
            _LOG.warning(
                "MCP aracı modele gönderilmedi: tam adı 128 karakteri aşıyor",
                extra={"sunucu": server, "arac": remote.name},
            )
            continue
        named.append((name, remote))
    return named

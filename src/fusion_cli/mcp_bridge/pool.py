"""MCP bağlantılarını sunucu başına oturum boyunca açık tutan havuz.

AnyIO yığınını açan gözetmen görevi kendi yığınını kapatır. Çağıranlar
bağlantıyı ödünç alır; iptal/kapanış stop sinyaliyle sahibine iletilir.
Değişen sunucu tek başına yenilenir, diğer bağlantılar korunur.
Olay döngüsü de sahipliğin parçasıdır: farklı loop görevi beklenmez.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from weakref import WeakKeyDictionary

from ..config.mcp_project_approval import is_noninteractive
from ..config.models import Config, HostedConnectorConfig, McpServerConfig, McpTransport
from ..config.paths import base_data_dir
from ..core.constants import MCP_NETWORK_TIMEOUT_S
from ..tools import ToolRegistry
from ..tools.mcp_background import cancel_mcp_background_calls
from .backoff import McpBackoff
from .client import McpClient, McpConnectionStatus, failure_status
from .failures import STATE_CONNECTED, STATE_LOGIN_REQUIRED, is_permanent_kind
from .hosted import AskSession, HostedConnectorClient
from .identity import duplicate_of, unique_configs, unique_hosted_configs
from .late_connect import LateConnections
from .lifecycle import drain_owned_tasks, wait_owned_task
from .oauth_flow import OAuthFlowOwner
from .references import McpCatalog
from .timeouts import startup_wait

__all__ = [
    "McpToolPool",
    "close_mcp_pool",
    "connected_mcp_client",
    "drop_mcp_connection",
    "ensure_hosted_tools",
    "ensure_mcp_tools",
    "forget_mcp_failure",
    "mcp_catalogs",
    "mcp_pool_statuses",
    "new_mcp_failures",
    "request_mcp_reconnect",
]

_LOG = logging.getLogger(__name__)

#: Başarısızlık olarak bildirilmeyen durumlar: bağlı ve giriş bekleyen (kullanıcı "Bağlan"a basar).
_SILENT_STATES = frozenset({STATE_CONNECTED, STATE_LOGIN_REQUIRED})


@dataclass(slots=True)
class _Entry:
    """Tek bir sunucunun canlı bağlantısı ve gözetmeni."""

    config: McpServerConfig
    loop: asyncio.AbstractEventLoop
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    client: McpClient | None = None
    error: Exception | None = None
    task: asyncio.Task[None] | None = None


@dataclass(frozen=True, slots=True)
class _Parked:
    """Kullanıcı bir şey yapmadan düzelmeyecek başarısızlık (ör. giriş gerekli)."""

    config: McpServerConfig
    status: McpConnectionStatus


class McpToolPool:
    """MCP istemcilerini sunucu başına, turlar arasında yeniden kullan."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._backoff = McpBackoff(clock)
        self.oauth_flows = OAuthFlowOwner(
            directory_factory=lambda: base_data_dir() / "mcp-oauth-locks"
        )
        self._entries: dict[str, _Entry] = {}
        self._parked: dict[str, _Parked] = {}
        #: Kopyası bildirilmiş bağlantı adları: uyarı oturumda BİR KEZ yazılır.
        self._reported_duplicates: set[str] = set()
        #: Kullanıcıya bildirilmiş (sunucu, tür) başarısızlıkları: aynısı oturumda BİR KEZ.
        self._reported_failures: set[tuple[str, str]] = set()
        #: Kilit olay döngüsü başına: `asyncio.Lock` ilk çekişmeli kullanımda o döngüye
        #: bağlanır, başka döngüden kullanım `RuntimeError` verirdi (masaüstünde birden
        #: çok döngü/iş parçacığı olabilir). Girdiler zaten döngüye bağlıdır (`_Entry.loop`).
        self._locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
            WeakKeyDictionary()
        )
        #: Kapanması istenmiş ama henüz bitmemiş gözetmen görevleri.
        #
        # İptal edilen bir `clients_for` çağrısı girdiyi `self._entries`'e ASLA
        # yazmaz; o girdinin görevi burada tutulmazsa `aclose()` onu bulamaz ve
        # stdio alt süreci oturumdan sağ çıkar.
        self._draining: set[asyncio.Task[None]] = set()
        self._draining_deadlines: dict[asyncio.Task[None], float] = {}
        #: `/mcp reconnect` ile düşürülmesi istenen sunucular: canlı girdi bir sonraki
        #: `clients_for`'da kapatılıp yeniden açılır (eşzamansız olmayan çağıranlar için; P-049).
        self._reconnect_requested: set[str] = set()
        #: Sunucu başına istem/kaynak kataloğu ve onu çeken istemci (P-049): bağlantı
        #: değişince (yeni istemci) yeniden çekilir, aynı bağlantıda bir kez. Çekim
        #: başarısızsa istemci `None` kalır: sonraki tur yeniden dener.
        self._catalogs: dict[str, tuple[McpClient | None, McpCatalog]] = {}
        #: Arka planda bağlanmayı sürdüren açılışlar (#239, `MCP_CONNECTION_NONBLOCKING`).
        self._connecting: dict[str, asyncio.Task[None]] = {}

    @property
    def _lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = self._locks.get(loop)
        if lock is None:
            lock = self._locks[loop] = asyncio.Lock()
        return lock

    @property
    def is_empty(self) -> bool:
        """Havuzda canlı bir bağlantı var mı? Başarısız giriş iz bırakmaz."""
        return not self._entries

    @property
    def statuses(self) -> dict[str, McpConnectionStatus]:
        """Havuzun bildiği sunucuların durumu: canlılar ve park edilenler."""
        result = {name: parked.status for name, parked in self._parked.items()}
        result.update(self._backoff.statuses)
        for name, entry in self._entries.items():
            status = entry.client.statuses.get(name) if entry.client else None
            if status is not None:
                result[name] = status
        return result

    def take_new_failures(self, names: Iterable[str]) -> tuple[McpConnectionStatus, ...]:
        """Verilen sunuculardan, daha önce bildirilmemiş başarısızlıkları ver ve işaretle.

        Giriş bekleyen sunucu başarısızlık sayılmaz (Bağlantılar ekranındaki "Bağlan"
        içindir). Aynı sunucunun aynı türden başarısızlığı yeniden denemelerde tekrar
        bildirilmez; tür değişirse ya da sunucu düzelip yeniden bozulursa bildirilir.
        """
        wanted = set(names)
        new: list[McpConnectionStatus] = []
        for name, status in self.statuses.items():
            if name not in wanted or status.state in _SILENT_STATES:
                continue
            key = (name, status.kind or status.state)
            if key in self._reported_failures:
                continue
            self._reported_failures.add(key)
            new.append(status)
        return tuple(new)

    def request_reconnect(self, name: str) -> None:
        """Sunucuya sonraki turda yeniden bağlan: park/backoff kaydı silinir, canlı oturum
        `clients_for`'da kapatılıp yeniden açılır. Eşzamansız bekleyemeyen çağıranlar
        (REPL `/mcp reconnect`) için `drop`'un ertelenmiş karşılığı."""
        self.forget(name)
        self._reconnect_requested.add(name)

    def forget(self, name: str) -> None:
        """Park edilmiş sunucuyu serbest bırak; sonraki tur yeniden dener.

        Kullanıcı "Bağlan" ile giriş yaptığında çağrılır: token artık anahtarlıkta
        ve sunucu turda kullanılabilir.
        """
        self._parked.pop(name, None)
        self._backoff.forget(name)
        self._reported_failures = {key for key in self._reported_failures if key[0] != name}

    async def clients_for(
        self, configs: tuple[McpServerConfig, ...], *, retry_delays_s: tuple[float, ...] = ()
    ) -> tuple[McpClient, ...]:
        """Kullanılabilir sunucuların istemcilerini ver; eksikleri eşzamanlı bağla."""
        self._report_duplicates(configs)
        wanted = tuple(
            replace(config, retry_delays_s=retry_delays_s)
            if config.retry_delays_s is None and retry_delays_s
            else config
            for config in unique_configs(configs)
        )
        loop = asyncio.get_running_loop()
        async with self._lock:
            await self._discard_stale(wanted, loop)
            # Başka (kapanmış) döngünün açılışı burada beklenemez; yeniden açılır.
            for name, task in tuple(self._connecting.items()):
                if task.get_loop() is not loop:
                    del self._connecting[name]
            to_open = [
                config
                for config in wanted
                if config.name not in self._entries
                and config.name not in self._connecting
                and not self._is_parked(config)
            ]
            await self._open_nonblocking(wanted, to_open, loop)
            return tuple(
                entry.client
                for config in wanted
                if (entry := self._entries.get(config.name)) is not None
                and entry.client is not None
            )

    async def _open_nonblocking(
        self,
        wanted: tuple[McpServerConfig, ...],
        to_open: list[McpServerConfig],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Claude Code açılışı (#239): kimin ne kadar bekleneceği `timeouts.startup_wait`'te.

        Süresinde bağlanamayan sunucu arka planda bağlanmayı sürdürür ve araçları sonraki
        turda deftere girer. Tur iptal edilse de açılış sürer; `aclose()` onu kapatır.
        """
        for config in to_open:
            task = loop.create_task(self._open(config, loop))
            self._connecting[config.name] = task
            task.add_done_callback(functools.partial(self._connected, config.name))
        names, cap = startup_wait(wanted, noninteractive=is_noninteractive())
        pending = [self._connecting[name] for name in names if name in self._connecting]
        if pending:
            await asyncio.wait(pending, timeout=cap)

    def _connected(self, name: str, task: asyncio.Task[None]) -> None:
        if self._connecting.get(name) is task:
            del self._connecting[name]
        if not task.cancelled() and task.exception() is not None:
            _LOG.warning("MCP arka plan bağlantısı düştü", extra={"sunucu": name})

    def connecting_tasks(self) -> dict[str, asyncio.Task[None]]:
        """Arka planda bağlanmayı süren açılışlar (bu döngüde)."""
        loop = asyncio.get_running_loop()
        return {
            name: task
            for name, task in self._connecting.items()
            if task.get_loop() is loop and not task.done()
        }

    def connected_client(self, name: str) -> McpClient | None:
        """Sunucunun bu döngüdeki canlı istemcisi; yoksa None."""
        entry = self._entries.get(name)
        return entry.client if entry is not None else None

    async def refresh_catalog(self, client: McpClient) -> None:
        """İstemcinin sunucuları için istem/kaynak kataloğunu (yalnız ilk kez) çek."""
        # Eski/sahte istemci katalog arayüzü taşımayabilir: katalog yok sayılır.
        for server in getattr(client, "servers", ()):
            cached = self._catalogs.get(server)
            stale = getattr(client, "catalog_stale", None)
            if cached is not None and cached[0] is client and not (stale and stale(server)):
                continue
            try:
                catalog = await client.catalog(server)
            except Exception as error:  # katalog bir zenginleştirme; tur düşmez, log'lanır
                # Ölçüldü (31 Ekim): geçici hata (zaman aşımı) boş katalog olarak bağlantı
                # ömrü boyunca önbelleğe yazılıyordu; `/mcp reconnect`'e kadar "istem
                # bulunamadı" alınıyordu. Artık bilinen son liste korunur ve yeniden denenir.
                _LOG.info(
                    "MCP istem/kaynak listesi alınamadı",
                    extra={"sunucu": server, "hata": type(error).__name__},
                )
                self._catalogs[server] = (None, cached[1] if cached else McpCatalog())
                continue
            self._catalogs[server] = (client, catalog)

    def catalogs(self) -> dict[str, McpCatalog]:
        """Sunucu → son bilinen katalog (bağlantısı düşmüş olanlar dahil, en son hâli)."""
        return {name: catalog for name, (_client, catalog) in self._catalogs.items()}

    def _report_duplicates(self, configs: tuple[McpServerConfig, ...]) -> None:
        for duplicate, original in duplicate_of(configs).items():
            if duplicate in self._reported_duplicates:
                continue
            self._reported_duplicates.add(duplicate)
            _LOG.warning(
                "Yinelenen MCP bağlantısı atlandı",
                extra={"sunucu": duplicate, "asil": original},
            )

    def _is_parked(self, config: McpServerConfig) -> bool:
        if self._backoff.is_waiting(config):
            return True
        parked = self._parked.get(config.name)
        if parked is None:
            return False
        if parked.config != config:
            # Kullanıcı bağlantıyı değiştirdi: eski başarısızlık artık geçersiz.
            self._parked.pop(config.name, None)
            return False
        return True

    async def _discard_stale(
        self, wanted: tuple[McpServerConfig, ...], loop: asyncio.AbstractEventLoop
    ) -> None:
        """İstenmeyen, değişmiş ya da ölü girdileri kapat."""
        by_name = {config.name: config for config in wanted}
        for name, entry in tuple(self._entries.items()):
            if (
                by_name.get(name) == entry.config
                and self._is_alive(entry, loop)
                and name not in self._reconnect_requested
            ):
                continue
            self._reconnect_requested.discard(name)
            del self._entries[name]
            await self._discard(entry, loop)

    @staticmethod
    def _is_alive(entry: _Entry, loop: asyncio.AbstractEventLoop) -> bool:
        if entry.loop is not loop or entry.client is None or entry.error is not None:
            return False
        if entry.client.is_stalled:
            return False
        return entry.task is not None and not entry.task.done()

    async def _open(self, config: McpServerConfig, loop: asyncio.AbstractEventLoop) -> None:
        entry = _Entry(config=config, loop=loop)
        entry.task = loop.create_task(self._supervise(entry))
        try:
            await entry.ready.wait()
        except BaseException:
            # İPTAL DE BURAYA DÜŞER ve asıl sızıntı yolu buydu: Ctrl-C ya da
            # `AppSession.close()` turu bağlantı kurulurken iptal ettiğinde girdi
            # havuza hiç yazılmıyor, gözetmen bağlanmayı bitirip `stop.wait()`'te
            # sonsuza park ediyor ve `aclose()` onu bulamıyordu. Burada beklemek
            # YANLIŞ olur: iptal edilmiş bağlamda her `await` anında yeniden
            # `CancelledError` verir. Bu yüzden yalnız kapanma işareti verilir ve
            # görev `aclose()`'un bekleyeceği kümeye alınır.
            self._drain(entry)
            raise
        status = self._entry_status(entry)
        if status.state == STATE_CONNECTED:
            self._backoff.forget(config.name)
            self._entries[config.name] = entry
            return
        # Başarısız sunucu havuzda TUTULMAZ; süreci/soketi hemen kapanır.
        self._drain(entry)
        await self._await_task(entry)
        self._record_failure(config, status)

    @staticmethod
    def _entry_status(entry: _Entry) -> McpConnectionStatus:
        name = entry.config.name
        if entry.error is not None:
            return failure_status(entry.config, entry.error, latency_ms=0)
        status = entry.client.statuses.get(name) if entry.client else None
        return status or McpConnectionStatus(server=name, state="hata")

    def _record_failure(self, config: McpServerConfig, status: McpConnectionStatus) -> None:
        if not is_permanent_kind(status.kind):
            self._backoff.record(config, status)
            return
        self._parked[config.name] = _Parked(config=config, status=status)
        # Kullanıcıya gürültüsüz, BİR KEZ: durum Bağlantılar ekranında görünür.
        level = logging.INFO if status.state == STATE_LOGIN_REQUIRED else logging.WARNING
        _LOG.log(
            level,
            "MCP sunucusu bu oturumda turlarda atlanacak",
            extra={"sunucu": config.name, "tur": status.kind},
        )

    def _drain(self, entry: _Entry) -> None:
        """Girdiye kapanma işareti ver ve görevini `aclose()` için kaydet.

        Beklemez: iptal edilmiş bağlamdan çağrılabilir olmak zorundadır. Gözetmen
        `stop` olayını görüp yığını KENDİ görevinde kapatır — `cancel()` değil
        `stop` kullanılır, çünkü düzenli kapanış alt süreci daha güvenli bırakır.
        """
        entry.stop.set()
        task = entry.task
        if task is None or task.done():
            return
        self._draining.add(task)
        budget = (
            entry.config.close_timeout_s
            if entry.config.close_timeout_s is not None
            else MCP_NETWORK_TIMEOUT_S
        )
        self._draining_deadlines.setdefault(task, entry.loop.time() + budget)
        task.add_done_callback(self._draining_done)

    def _draining_done(self, task: asyncio.Task[None]) -> None:
        self._draining.discard(task)
        self._draining_deadlines.pop(task, None)

    async def _supervise(self, entry: _Entry) -> None:
        """Yığını AÇ, kapatma istenene kadar tut, kendi görevinde kapat."""
        try:
            # TUR YOLU ETKİLEŞİMSİZDİR: giriş penceresi yalnız kullanıcının
            # "Bağlan" eyleminde açılır (bkz. `oauth.LoopbackOAuthCallback`).
            async with McpClient((entry.config,), interactive=False) as client:
                client.reauth = self._reauth  # 401/403'te headersHelper yeniden (#249)
                entry.client = client
                entry.ready.set()
                await entry.stop.wait()
        except Exception as error:
            # İptal YUTULMAZ: yalnız gerçek bağlantı hataları duruma yazılır.
            entry.error = error
        finally:
            entry.ready.set()

    async def _discard(self, entry: _Entry, loop: asyncio.AbstractEventLoop) -> None:
        """Girdiyi kapat; yalnız AYNI döngüde beklenebilir."""
        if entry.loop is not loop:
            # Ölü döngüdeki görev beklenemez; beklemek süreci kilitler.
            _LOG.warning("MCP havuzu farklı olay döngüsünde bulundu, bırakıldı")
            return
        self._drain(entry)
        await self._await_task(entry)

    async def drop(self, name: str) -> None:
        """Adı verilen sunucunun canlı oturumunu kapat ve park kaydını sil.

        Kullanıcı çıkış yaptığında anahtarlık silinir ama canlı oturum bellekteki
        token'la çalışmaya devam ederdi.
        """
        loop = asyncio.get_running_loop()
        async with self._lock:
            entry = self._entries.pop(name, None)
            if entry is not None:
                await self._discard(entry, loop)
        self.forget(name)

    async def _reauth(self, name: str) -> McpClient | None:
        """Sunucuyu kapatıp yeniden bağla: bağlantıda headersHelper taze başlık üretir (#249)."""
        entry = self._entries.get(name)
        if entry is None:
            return None
        config = entry.config
        await self.drop(name)
        clients = await self.clients_for((config,))
        return clients[0] if clients else None

    async def discard_client(self, client: McpClient) -> None:
        """Kullanım sırasında bozulan istemciyi bırak; sonraki tur yeniden bağlanır."""
        loop = asyncio.get_running_loop()
        async with self._lock:
            for name, entry in tuple(self._entries.items()):
                if entry.client is client:
                    del self._entries[name]
                    await self._discard(entry, loop)

    async def _await_task(self, entry: _Entry) -> None:
        if entry.task is None:
            return
        remaining = self._draining_deadlines.get(entry.task, entry.loop.time()) - entry.loop.time()
        await wait_owned_task(entry.task, remaining)

    async def aclose(self) -> None:
        """Oturum biterken bağlantıları kapat; stdio alt süreçleri sahipsiz kalmasın."""
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        connecting = tuple(t for t in self._connecting.values() if t.get_loop() is current)
        self._connecting.clear()
        for task in connecting:
            task.cancel()
        if connecting:
            await asyncio.gather(*connecting, return_exceptions=True)
        async with self._lock:
            entries = tuple(self._entries.values())
            self._entries.clear()
            self._parked.clear()
            self._backoff.clear()
            self._reported_failures.clear()
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._draining.clear()
                return
            for entry in entries:
                await self._discard(entry, loop)
            await self._drain_pending(loop)

    async def _drain_pending(self, loop: asyncio.AbstractEventLoop) -> None:
        """Önceden sahiplenilmiş kapanışların kalan bütçesini tüket."""
        await drain_owned_tasks(self._draining, self._draining_deadlines, loop)


_POOL = McpToolPool()
_LATE = LateConnections()


def mcp_oauth_flows() -> OAuthFlowOwner:
    """Yeni singleton yerine mevcut havuzun OAuth sahibini kullan."""
    return _POOL.oauth_flows


def with_project_dir(
    configs: tuple[McpServerConfig, ...], root: Path | None
) -> tuple[McpServerConfig, ...]:
    """Stdio sunucularına oturum kökünü damgala (`CLAUDE_PROJECT_DIR`, #273).

    Havuz süreç başına tektir; kök yapılandırmanın parçası olduğu için başka projenin
    oturumu aynı sunucuyu kendi köküyle yeniden açar.
    """
    if root is None:
        return configs
    return tuple(
        replace(config, project_dir=str(root))
        if config.transport is McpTransport.STDIO and not config.project_dir
        else config
        for config in configs
    )


async def ensure_mcp_tools(
    configs: tuple[McpServerConfig, ...],
    registry: ToolRegistry,
    *,
    retry_delays_s: tuple[float, ...] = (),
    root: Path | None = None,
) -> tuple[str, ...]:
    """Bağlan (ya da açık bağlantıları kullan) ve araçları kayıt defterine ekle.

    Kayıt her turda tekrar çağrılır. `ToolRegistry.register` yinelenen adda
    `FusionError` fırlatır — uzak araçlar bu yüzden `register_or_replace` ile
    yazılır: bağlantı artık oturum boyunca yaşadığı için aynı defter ikinci turda
    yeniden beslenebilir ve keşif taze şema getirir.

    Bir sunucunun keşfi düşerse diğerlerinin araçları yine eklenir.
    """
    configs = with_project_dir(configs, root)
    added: list[str] = []
    for client in await _POOL.clients_for(configs, retry_delays_s=retry_delays_s):
        try:
            added.extend(await client.register_into(registry))
        except Exception as error:  # tek sunucunun kopması turu düşürmez; log'lanır
            _LOG.warning("MCP araç keşfi başarısız", extra={"hata": type(error).__name__})
            await _POOL.discard_client(client)
            continue
        # İstem/kaynak kataloğu (P-049): `/mcp__s__p` tamamlaması ve `@s:kaynak` için.
        await _POOL.refresh_catalog(client)
    # Arka planda bağlanmayı sürenler bitince araçları bu deftere aynı turda girer (#239).
    _LATE.schedule(_POOL, registry, configs)
    return tuple(added)


def mcp_catalogs() -> dict[str, McpCatalog]:
    """Bilinen sunucuların istem/kaynak kataloğu (senkron; slash tamamlama için)."""
    return _POOL.catalogs()


def connected_mcp_client(name: str) -> McpClient | None:
    """Sunucunun canlı istemcisi (tur içinde, bağlantı kurulduktan sonra)."""
    return _POOL.connected_client(name)


def new_mcp_failures(configs: tuple[McpServerConfig, ...]) -> tuple[McpConnectionStatus, ...]:
    """Bu turda ilk kez görülen bağlantı başarısızlıkları (kullanıcıya tek satır göstermek için)."""
    return _POOL.take_new_failures(config.name for config in configs)


def mcp_pool_statuses() -> dict[str, McpConnectionStatus]:
    """Turların gördüğü sunucu durumları (Bağlantılar ekranı için)."""
    return _POOL.statuses


async def drop_mcp_connection(name: str) -> None:
    """Çıkış yapılan sunucunun havuzdaki canlı oturumunu kapat."""
    await _POOL.drop(name)


def forget_mcp_failure(name: str) -> None:
    """Kullanıcı sunucuyu düzelttiğinde (giriş vb.) park kaydını kaldır."""
    _POOL.forget(name)


def request_mcp_reconnect(name: str) -> None:
    """`/mcp reconnect <ad>`: sonraki turda bağlantıyı kapatıp yeniden kur (P-049)."""
    _POOL.request_reconnect(name)


def _hosted_channel_factory(config: Config) -> AskSession:
    """Gerçek kanalı kur. Ayrı fonksiyon: test yerine geçebilsin."""
    from ..providers.hosted_bridge import HostedSessionChannel

    return HostedSessionChannel(config)


#: Barındırmalı connector kanalı TURLAR ARASI yaşar.
#
# `providers/hosted_bridge.py` konuşmanın sürekli olmasını şart koşuyor: kanalı her
# turda yeniden kurmak geçmişi çöpe atar, her tur yeni bir keşif turu harcanır ve
# connector bağlamı kaybolur. Anahtar yapılandırmadır: kullanıcı bağlantı ekleyip
# çıkardığında kanal yenilenmelidir.
_HOSTED: tuple[object, AskSession] | None = None
#: Aynı yapılandırma için tur arası yaşayan connector istemcisi (keşif önbelleği onda).
_HOSTED_CLIENT: tuple[object, HostedConnectorClient] | None = None


def _hosted_channel(config: Config) -> AskSession:
    global _HOSTED
    key = (config.hosted_connectors, config.web_sessions)
    if _HOSTED is not None and _HOSTED[0] == key:
        return _HOSTED[1]
    channel = _hosted_channel_factory(config)
    _HOSTED = (key, channel)
    return channel


def _policy_connectors(
    config: Config, root: Path | None = None
) -> tuple[HostedConnectorConfig, ...]:
    """Kuruluş politikası (#274): tekelde connector'lar düşer (allowAllClaudeAiMcps hariç),
    ret/izin listesi uygulanır. Yapılandırma süzülmez: kullanıcının kaydı silinmesin.

    Proje katmanı oturum kökünden okunur: masaüstünde proje değişince süreç cwd'si eski
    projede kalır ve proje `deniedMcpServers` listesi connector'lara uygulanmıyordu."""
    import os

    from ..config.mcp_policy import filter_hosted_connectors, load_policy

    policy = load_policy(root if root is not None else Path.cwd())
    return filter_hosted_connectors(config.hosted_connectors, policy, os.environ)


async def ensure_hosted_tools(
    config: Config, registry: ToolRegistry, *, root: Path | None = None
) -> tuple[str, ...]:
    """Sağlayıcı-barındırmalı connector araçlarını kayıt defterine ekle.

    MCP havuzundan AYRIDIR: burada tutulacak bir bağlantı yoktur, araçlar
    sağlayıcının oturumunda yaşar. Doğrulanmamış connector için oturuma hiç
    gidilmez (bkz. `mcp_bridge/hosted.py::register_into`).
    """
    if not config.hosted_connectors:
        return ()
    # Kopya connector ayıklanır. `mcp_servers` bu korumayı `unique_configs` ile
    # zaten alıyordu; barındırmalı connector'lar dışarıda kalmıştı ve aynı Meta
    # Ads adresi iki kez kayıt defterine giriyordu (ölçüldü, 22 Eylül).
    benzersiz = unique_hosted_configs(_policy_connectors(config, root))
    if not benzersiz:
        return ()
    # İstemci de kanal gibi turlar arası yaşar: keşif sonucu onda önbelleklenir ve
    # her tur kullanıcının sağlayıcı ekranına yeni bir keşif metni yazılmaz.
    global _HOSTED_CLIENT
    key = (benzersiz, config.web_sessions)
    if _HOSTED_CLIENT is None or _HOSTED_CLIENT[0] != key:
        _HOSTED_CLIENT = (key, HostedConnectorClient(benzersiz, ask=_hosted_channel(config)))
    return await _HOSTED_CLIENT[1].register_into(registry)


async def close_mcp_pool() -> None:
    """Süreç/oturum biterken açık MCP bağlantılarını kapat."""
    # Önce arka plana taşınmış çağrılar (#233): bağlantı kapanınca zaten düşerlerdi.
    await cancel_mcp_background_calls()
    await _LATE.cancel_all()
    await _POOL.aclose()

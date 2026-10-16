"""MCP bağlantılarını sunucu başına oturum boyunca açık tutan havuz.

AnyIO yığınını açan gözetmen görevi kendi yığınını kapatır. Çağıranlar
bağlantıyı ödünç alır; iptal/kapanış stop sinyaliyle sahibine iletilir.
Değişen sunucu tek başına yenilenir, diğer bağlantılar korunur.
Olay döngüsü de sahipliğin parçasıdır: farklı loop görevi beklenmez.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from ..config.models import Config, McpServerConfig
from ..config.paths import base_data_dir
from ..core.constants import MCP_NETWORK_TIMEOUT_S
from ..tools import ToolRegistry
from .backoff import McpBackoff
from .client import McpClient, McpConnectionStatus, failure_status
from .failures import STATE_CONNECTED, STATE_LOGIN_REQUIRED, is_permanent_kind
from .hosted import AskSession
from .identity import duplicate_of, unique_configs, unique_hosted_configs
from .lifecycle import drain_owned_tasks, wait_owned_task
from .oauth_flow import OAuthFlowOwner

__all__ = [
    "McpToolPool",
    "close_mcp_pool",
    "ensure_hosted_tools",
    "ensure_mcp_tools",
    "forget_mcp_failure",
    "mcp_pool_statuses",
]

_LOG = logging.getLogger(__name__)


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
        self._lock = asyncio.Lock()
        #: Kapanması istenmiş ama henüz bitmemiş gözetmen görevleri.
        #
        # İptal edilen bir `clients_for` çağrısı girdiyi `self._entries`'e ASLA
        # yazmaz; o girdinin görevi burada tutulmazsa `aclose()` onu bulamaz ve
        # stdio alt süreci oturumdan sağ çıkar.
        self._draining: set[asyncio.Task[None]] = set()
        self._draining_deadlines: dict[asyncio.Task[None], float] = {}

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

    def forget(self, name: str) -> None:
        """Park edilmiş sunucuyu serbest bırak; sonraki tur yeniden dener.

        Kullanıcı "Bağlan" ile giriş yaptığında çağrılır: token artık anahtarlıkta
        ve sunucu turda kullanılabilir.
        """
        self._parked.pop(name, None)
        self._backoff.forget(name)

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
            to_open = [
                config
                for config in wanted
                if config.name not in self._entries and not self._is_parked(config)
            ]
            if to_open:
                # İptal gather'dan çocuklara geçer; her `_open` kendi gözetmenini
                # boşaltma kümesine alır (bkz. `_open`).
                await asyncio.gather(*(self._open(config, loop) for config in to_open))
            return tuple(
                entry.client
                for config in wanted
                if (entry := self._entries.get(config.name)) is not None
                and entry.client is not None
            )

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
            if by_name.get(name) == entry.config and self._is_alive(entry, loop):
                continue
            del self._entries[name]
            await self._discard(entry, loop)

    @staticmethod
    def _is_alive(entry: _Entry, loop: asyncio.AbstractEventLoop) -> bool:
        if entry.loop is not loop or entry.client is None or entry.error is not None:
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
        async with self._lock:
            entries = tuple(self._entries.values())
            self._entries.clear()
            self._parked.clear()
            self._backoff.clear()
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


def mcp_oauth_flows() -> OAuthFlowOwner:
    """Yeni singleton yerine mevcut havuzun OAuth sahibini kullan."""
    return _POOL.oauth_flows


async def ensure_mcp_tools(
    configs: tuple[McpServerConfig, ...],
    registry: ToolRegistry,
    *,
    retry_delays_s: tuple[float, ...] = (),
) -> tuple[str, ...]:
    """Bağlan (ya da açık bağlantıları kullan) ve araçları kayıt defterine ekle.

    Kayıt her turda tekrar çağrılır. `ToolRegistry.register` yinelenen adda
    `FusionError` fırlatır — uzak araçlar bu yüzden `register_or_replace` ile
    yazılır: bağlantı artık oturum boyunca yaşadığı için aynı defter ikinci turda
    yeniden beslenebilir ve keşif taze şema getirir.

    Bir sunucunun keşfi düşerse diğerlerinin araçları yine eklenir.
    """
    added: list[str] = []
    for client in await _POOL.clients_for(configs, retry_delays_s=retry_delays_s):
        try:
            added.extend(await client.register_into(registry))
        except Exception as error:  # tek sunucunun kopması turu düşürmez; log'lanır
            _LOG.warning("MCP araç keşfi başarısız", extra={"hata": type(error).__name__})
            await _POOL.discard_client(client)
    return tuple(added)


def mcp_pool_statuses() -> dict[str, McpConnectionStatus]:
    """Turların gördüğü sunucu durumları (Bağlantılar ekranı için)."""
    return _POOL.statuses


def forget_mcp_failure(name: str) -> None:
    """Kullanıcı sunucuyu düzelttiğinde (giriş vb.) park kaydını kaldır."""
    _POOL.forget(name)


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


def _hosted_channel(config: Config) -> AskSession:
    global _HOSTED
    key = (config.hosted_connectors, config.web_sessions)
    if _HOSTED is not None and _HOSTED[0] == key:
        return _HOSTED[1]
    channel = _hosted_channel_factory(config)
    _HOSTED = (key, channel)
    return channel


async def ensure_hosted_tools(config: Config, registry: ToolRegistry) -> tuple[str, ...]:
    """Sağlayıcı-barındırmalı connector araçlarını kayıt defterine ekle.

    MCP havuzundan AYRIDIR: burada tutulacak bir bağlantı yoktur, araçlar
    sağlayıcının oturumunda yaşar. Doğrulanmamış connector için oturuma hiç
    gidilmez (bkz. `mcp_bridge/hosted.py::register_into`).
    """
    if not config.hosted_connectors:
        return ()
    from .hosted import HostedConnectorClient

    # Kopya connector ayıklanır. `mcp_servers` bu korumayı `unique_configs` ile
    # zaten alıyordu; barındırmalı connector'lar dışarıda kalmıştı ve aynı Meta
    # Ads adresi iki kez kayıt defterine giriyordu (ölçüldü, 22 Eylül).
    benzersiz = unique_hosted_configs(config.hosted_connectors)
    client = HostedConnectorClient(benzersiz, ask=_hosted_channel(config))
    return await client.register_into(registry)


async def close_mcp_pool() -> None:
    """Süreç/oturum biterken açık MCP bağlantılarını kapat."""
    await _POOL.aclose()

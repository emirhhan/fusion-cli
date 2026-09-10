"""MCP bağlantılarını OTURUM boyunca açık tutan havuz.

Neden gerekli — ölçülmüş maliyet:

Üç çağrı yeri (`cli/session.py`, `cli/app.py`, `cli/repl/loop.py`) HER TURDA
`async with McpClient(...)` açıyordu. Her tur stdio sunucusunu yeniden
başlatıyor (`npx -y @coding-solo/godot-mcp`) ve uzak sunucu için yetkilendirmeyi
yeniden deniyordu; Meta Ads bağlıyken bu, tur başına 10 saniyelik bir zaman
aşımı demekti. Bağlantı bir turun değil OTURUMUN kaynağıdır.

YIĞIN AÇILDIĞI GÖREVDE KAPATILMAK ZORUNDADIR. `stdio_client` ve
`streamablehttp_client` anyio görev grupları kurar; bir cancel scope'u başka
görevde terk etmek `RuntimeError` fırlatır. Teardown ise başka bir görevden
gelir (`AppSession.close`, `fusion agent` çıkışı). Bu yüzden bağlantının ömrü
ayrı bir GÖZETMEN görevine verilir: gözetmen yığını açar, turlar hazır istemciyi
ödünç alır, kapatma isteği gözetmene bir olayla bildirilir ve yığın kendi
görevinde kapanır.

Olay döngüsü de anahtarın parçasıdır: ölü bir döngüde kalan görev beklenemez,
bu yüzden farklı döngü önbellek ıskasıdır (bkz. `_Entry.loop`).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ..config.models import Config, McpServerConfig
from ..tools import ToolRegistry
from .client import McpClient
from .hosted import AskSession

__all__ = ["McpToolPool", "close_mcp_pool", "ensure_hosted_tools", "ensure_mcp_tools"]

_LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class _Entry:
    """Tek bir yapılandırma kümesi için canlı bağlantı ve gözetmeni."""

    configs: tuple[McpServerConfig, ...]
    loop: asyncio.AbstractEventLoop
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    client: McpClient | None = None
    error: BaseException | None = None
    task: asyncio.Task[None] | None = None


class McpToolPool:
    """Aynı yapılandırma için MCP istemcisini turlar arasında yeniden kullan."""

    def __init__(self) -> None:
        self._entry: _Entry | None = None
        self._lock = asyncio.Lock()
        #: Kapanması istenmiş ama henüz bitmemiş gözetmen görevleri.
        #
        # İptal edilen bir `client_for` çağrısı girdiyi `self._entry`'ye ASLA
        # yazmaz; o girdinin görevi burada tutulmazsa `aclose()` onu bulamaz ve
        # stdio alt süreci oturumdan sağ çıkar.
        self._draining: set[asyncio.Task[None]] = set()

    @property
    def is_empty(self) -> bool:
        """Havuzda canlı bir bağlantı var mı? Başarısız giriş iz bırakmaz."""
        return self._entry is None

    async def client_for(self, configs: tuple[McpServerConfig, ...]) -> McpClient:
        """Yapılandırma için istemci ver; varsa ödünç, yoksa yeni bağlan."""
        wanted = tuple(configs)
        loop = asyncio.get_running_loop()
        async with self._lock:
            current = self._entry
            if current is not None and self._reusable(current, wanted, loop):
                assert current.client is not None  # `_reusable` bunu garanti eder
                return current.client
            if current is not None:
                await self._discard(current, loop)
            return await self._open(wanted, loop)

    def _reusable(
        self, entry: _Entry, wanted: tuple[McpServerConfig, ...], loop: asyncio.AbstractEventLoop
    ) -> bool:
        if entry.configs != wanted or entry.loop is not loop:
            return False
        if entry.client is None or entry.error is not None:
            return False
        return entry.task is not None and not entry.task.done()

    async def _open(
        self, configs: tuple[McpServerConfig, ...], loop: asyncio.AbstractEventLoop
    ) -> McpClient:
        entry = _Entry(configs=configs, loop=loop)
        entry.task = loop.create_task(self._supervise(entry))
        try:
            await entry.ready.wait()
        except BaseException:
            # İPTAL DE BURAYA DÜŞER ve asıl sızıntı yolu buydu: Ctrl-C ya da
            # `AppSession.close()` turu bağlantı kurulurken iptal ettiğinde girdi
            # `self._entry`'ye hiç yazılmıyor, gözetmen bağlanmayı bitirip
            # `stop.wait()`'te sonsuza park ediyor ve `aclose()` onu bulamıyordu.
            # Burada beklemek YANLIŞ olur: iptal edilmiş bağlamda her `await`
            # anında yeniden `CancelledError` verir. Bu yüzden yalnız kapanma
            # işareti verilir ve görev `aclose()`'un bekleyeceği kümeye alınır.
            self._drain(entry)
            raise
        if entry.error is not None or entry.client is None:
            # Başarısız giriş ÖNBELLEĞE YAZILMAZ: sonraki tur yeniden denemeli,
            # aksi hâlde tek geçici arıza oturumun kalanını araçsız bırakırdı.
            entry.stop.set()
            await self._await_task(entry)
            raise entry.error or RuntimeError("MCP bağlantısı kurulamadı.")
        self._entry = entry
        return entry.client

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
        task.add_done_callback(self._draining.discard)

    async def _supervise(self, entry: _Entry) -> None:
        """Yığını AÇ, kapatma istenene kadar tut, kendi görevinde kapat."""
        try:
            async with McpClient(entry.configs) as client:
                entry.client = client
                entry.ready.set()
                await entry.stop.wait()
        except Exception as error:
            # İptal YUTULMAZ: yalnız gerçek bağlantı hataları duruma yazılır.
            entry.error = error
        finally:
            entry.ready.set()

    async def _discard(self, entry: _Entry, loop: asyncio.AbstractEventLoop) -> None:
        """Eski girdiyi bırak; yalnız AYNI döngüde kapatılabilir."""
        self._entry = None
        if entry.loop is not loop:
            # Ölü döngüdeki görev beklenemez; beklemek süreci kilitler.
            _LOG.warning("MCP havuzu farklı olay döngüsünde bulundu, bırakıldı")
            return
        entry.stop.set()
        await self._await_task(entry)

    async def _await_task(self, entry: _Entry) -> None:
        task = entry.task
        if task is None or task.done():
            return
        try:
            await task
        except Exception as error:  # kapanış hatası turu düşürmez
            _LOG.warning("MCP bağlantısı kapatılırken hata", extra={"hata": repr(error)})

    async def aclose(self) -> None:
        """Oturum biterken bağlantıları kapat; stdio alt süreçleri sahipsiz kalmasın."""
        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._entry = None
                self._draining.clear()
                return
            entry = self._entry
            if entry is not None:
                await self._discard(entry, loop)
            await self._drain_pending(loop)

    async def _drain_pending(self, loop: asyncio.AbstractEventLoop) -> None:
        """İptal yüzünden sahipsiz kalmış gözetmen görevlerinin bitmesini bekle."""
        pending = tuple(task for task in self._draining if task.get_loop() is loop)
        self._draining.difference_update(pending)
        if not pending:
            return
        results = await asyncio.gather(*pending, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                _LOG.warning("MCP bağlantısı kapanışta hata verdi", extra={"hata": repr(result)})


_POOL = McpToolPool()


async def ensure_mcp_tools(
    configs: tuple[McpServerConfig, ...], registry: ToolRegistry
) -> tuple[str, ...]:
    """Bağlan (ya da açık bağlantıyı kullan) ve araçları kayıt defterine ekle.

    Kayıt her turda tekrar çağrılır. `ToolRegistry.register` yinelenen adda
    `FusionError` fırlatır — uzak araçlar bu yüzden `register_or_replace` ile
    yazılır: bağlantı artık oturum boyunca yaşadığı için aynı defter ikinci turda
    yeniden beslenebilir ve keşif taze şema getirir.
    """
    client = await _POOL.client_for(configs)
    return await client.register_into(registry)


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

    client = HostedConnectorClient(config.hosted_connectors, ask=_hosted_channel(config))
    return await client.register_into(registry)


async def close_mcp_pool() -> None:
    """Süreç/oturum biterken açık MCP bağlantılarını kapat."""
    await _POOL.aclose()

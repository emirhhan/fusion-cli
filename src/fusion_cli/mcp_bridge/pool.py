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

SUNUCU BAŞINA HAVUZ (17 Eylül denetimi): havuz eskiden bütün yapılandırma
kümesini tek girdi tutuyordu. Kullanıcı bir bağlantıyı kapatıp açınca ya da yeni
bir bağlantı ekleyince BÜTÜN sunucular yeniden başlıyordu; sunucular da sırayla
bağlandığı için tur başı gecikme her sunucunun süresinin TOPLAMIYDI. Artık her
sunucunun kendi gözetmeni var, bağlantılar eşzamanlı kurulur ve yalnız değişen
sunucu yenilenir.

KENDİLİĞİNDEN DÜZELMEYEN BAŞARISIZLIK TURDA TEKRAR DENENMEZ: girişi yapılmamış
OAuth sunucusu (Notion), kurulu olmayan çalıştırıcı (uvx), reddedilen token… Bunlar
kullanıcı bir şey yapmadan düzelmez; her turda yeniden denemek her turda aynı hata
dökümü ve gecikme demekti. Sunucu bir kez sessizce "park edilir", durumu
Bağlantılar ekranında görünür (bkz. `service.McpConnectionService.statuses`);
kullanıcı giriş yapınca ya da bağlantıyı değiştirince park kalkar. Geçici
arızalar (zaman aşımı, ağ) önbelleğe yazılmaz: sonraki tur yeniden dener.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ..config.models import Config, McpServerConfig
from ..tools import ToolRegistry
from .client import McpClient, McpConnectionStatus, failure_status
from .failures import STATE_CONNECTED, STATE_LOGIN_REQUIRED, is_permanent_kind
from .hosted import AskSession
from .identity import duplicate_of, unique_configs, unique_hosted_configs

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

    def __init__(self) -> None:
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

    @property
    def is_empty(self) -> bool:
        """Havuzda canlı bir bağlantı var mı? Başarısız giriş iz bırakmaz."""
        return not self._entries

    @property
    def statuses(self) -> dict[str, McpConnectionStatus]:
        """Havuzun bildiği sunucuların durumu: canlılar ve park edilenler."""
        result = {name: parked.status for name, parked in self._parked.items()}
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

    async def clients_for(self, configs: tuple[McpServerConfig, ...]) -> tuple[McpClient, ...]:
        """Kullanılabilir sunucuların istemcilerini ver; eksikleri eşzamanlı bağla."""
        self._report_duplicates(configs)
        wanted = unique_configs(configs)
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
            self._entries[config.name] = entry
            return
        # Başarısız sunucu havuzda TUTULMAZ; süreci/soketi hemen kapanır.
        entry.stop.set()
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
            # Geçici arıza ÖNBELLEĞE YAZILMAZ: sonraki tur yeniden denemeli, aksi
            # hâlde tek bir ağ kesintisi oturumun kalanını araçsız bırakırdı.
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
        task.add_done_callback(self._draining.discard)

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
        entry.stop.set()
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
            entries = tuple(self._entries.values())
            self._entries.clear()
            self._parked.clear()
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._draining.clear()
                return
            for entry in entries:
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
    """Bağlan (ya da açık bağlantıları kullan) ve araçları kayıt defterine ekle.

    Kayıt her turda tekrar çağrılır. `ToolRegistry.register` yinelenen adda
    `FusionError` fırlatır — uzak araçlar bu yüzden `register_or_replace` ile
    yazılır: bağlantı artık oturum boyunca yaşadığı için aynı defter ikinci turda
    yeniden beslenebilir ve keşif taze şema getirir.

    Bir sunucunun keşfi düşerse diğerlerinin araçları yine eklenir.
    """
    added: list[str] = []
    for client in await _POOL.clients_for(configs):
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

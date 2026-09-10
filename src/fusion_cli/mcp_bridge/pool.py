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

from ..config.models import McpServerConfig
from ..tools import ToolRegistry
from .client import McpClient

__all__ = ["McpToolPool", "close_mcp_pool", "ensure_mcp_tools"]

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
        await entry.ready.wait()
        if entry.error is not None or entry.client is None:
            # Başarısız giriş ÖNBELLEĞE YAZILMAZ: sonraki tur yeniden denemeli,
            # aksi hâlde tek geçici arıza oturumun kalanını araçsız bırakırdı.
            entry.stop.set()
            await self._await_task(entry)
            raise entry.error or RuntimeError("MCP bağlantısı kurulamadı.")
        self._entry = entry
        return entry.client

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
            entry = self._entry
            if entry is None:
                return
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._entry = None
                return
            await self._discard(entry, loop)


_POOL = McpToolPool()


async def ensure_mcp_tools(
    configs: tuple[McpServerConfig, ...], registry: ToolRegistry
) -> tuple[str, ...]:
    """Bağlan (ya da açık bağlantıyı kullan) ve araçları kayıt defterine ekle.

    Kayıt her turda tekrar çağrılır: `ToolRegistry.register` aynı adı üzerine
    yazar, bu yüzden tekrar eklemek zararsızdır ve taze şema taşır.
    """
    client = await _POOL.client_for(configs)
    return await client.register_into(registry)


async def close_mcp_pool() -> None:
    """Süreç/oturum biterken açık MCP bağlantılarını kapat."""
    await _POOL.aclose()

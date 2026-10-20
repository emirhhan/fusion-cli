"""MCP bağlantılarını arayüzlerden bağımsız yöneten durum hizmeti."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace

from ..config.models import McpServerConfig
from .client import McpClient, McpConnectionStatus, failure_status
from .failures import STATE_CONNECTED
from .pool import forget_mcp_failure, mcp_oauth_flows, mcp_pool_statuses
from .tokens import KeyringTokenStorage

Probe = Callable[[McpServerConfig], Awaitable[McpConnectionStatus]]
PoolStatuses = Callable[[], dict[str, McpConnectionStatus]]


class McpConnectionService:
    def __init__(
        self,
        *,
        probe: Probe | None = None,
        quiet_probe: Probe | None = None,
        pool_statuses: PoolStatuses = mcp_pool_statuses,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._probe = probe or self._probe_server
        #: Giriş penceresi AÇMAYAN deneme: kaydetmeden önceki doğrulama bunu
        #: kullanır; giriş isteyen sunucu "giris_gerekli" döner, tarayıcı fırlamaz.
        self._quiet_probe = quiet_probe or self._probe_server_quietly
        self._pool_statuses = pool_statuses
        self._tasks: dict[str, asyncio.Task[McpConnectionStatus]] = {}
        self._statuses: dict[str, McpConnectionStatus] = {}
        self._sources: dict[str, McpServerConfig] = {}
        self._generations: dict[str, int] = {}
        self._retired: set[asyncio.Task[McpConnectionStatus]] = set()

    @property
    def statuses(self) -> dict[str, McpConnectionStatus]:
        """Ekranın göreceği durumlar.

        Kullanıcının hiç test etmediği bir sunucunun durumu turlardan gelir: girişi
        yapılmamış bir OAuth sunucusu turda sessizce atlanır ve kullanıcı bunu
        Bağlantılar ekranında "Giriş gerekli" + "Bağlan" olarak görür. Kullanıcının
        kendi denemesi (test/giriş) daha tazedir ve önceliklidir.
        """
        own = {name: self.login_status(name) for name in set(self._statuses) | set(self._tasks)}
        merged = self._pool_statuses()
        for name, status in own.items():
            pooled = merged.get(name)
            if pooled is None or status.observed_at >= pooled.observed_at:
                merged[name] = status
        return merged

    async def test(self, config: McpServerConfig) -> McpConnectionStatus:
        generation = self._admit(config)
        status = await self._probe(config)
        if generation == self._generations.get(config.name, 0):
            self._record(config.name, status)
        return status

    async def verify(self, config: McpServerConfig) -> McpConnectionStatus:
        """Kaydetmeden önce bağlantıyı dene; giriş penceresi açma."""
        generation = self._admit(config)
        status = await self._quiet_probe(config)
        if generation == self._generations.get(config.name, 0):
            self._record(config.name, status)
        return status

    def invalidate(self, name: str) -> None:
        """Eski kaynağa ait gözlemleri ve giriş görevlerini geçersizleştir."""
        self._generations[name] = self._generations.get(name, 0) + 1
        self._sources.pop(name, None)
        self._statuses.pop(name, None)
        task = self._tasks.pop(name, None)
        if task is not None:
            task.cancel()
            self._retired.add(task)
            task.add_done_callback(self._retire_done)

    def _retire_done(self, task: asyncio.Task[McpConnectionStatus]) -> None:
        self._retired.discard(task)
        if not task.cancelled():
            task.exception()

    def _admit(self, config: McpServerConfig) -> int:
        previous = self._sources.get(config.name)
        if previous != config:
            self.invalidate(config.name)
        self._sources[config.name] = config
        return self._generations.get(config.name, 0)

    def _record(self, name: str, status: McpConnectionStatus) -> None:
        self._statuses[name] = (
            status if status.observed_at else replace(status, observed_at=self._clock())
        )
        if status.state == STATE_CONNECTED:
            # Kullanıcı sunucuyu düzeltti (giriş yaptı, token'ı yeniledi): turlar
            # onu artık atlamamalı.
            forget_mcp_failure(name)

    def start_login(self, config: McpServerConfig) -> McpConnectionStatus:
        self._admit(config)
        current = self._tasks.get(config.name)
        if current is None or current.done():
            self._tasks[config.name] = asyncio.create_task(self._run_probe(config))
        pending = McpConnectionStatus(
            server=config.name, state="giris_bekleniyor", observed_at=self._clock()
        )
        self._statuses[config.name] = pending
        return pending

    def login_status(self, name: str) -> McpConnectionStatus:
        task = self._tasks.get(name)
        if task is not None and task.done():
            if task.cancelled():
                # İptal edilmiş görevin `result()`'ı CancelledError fırlatır ve
                # `baglanti.listele` isteğini düşürürdü.
                status = McpConnectionStatus(server=name, state="kapali")
            else:
                try:
                    status = task.result()
                except Exception:
                    status = McpConnectionStatus(
                        server=name, state="hata", message="MCP girişi tamamlanamadı."
                    )
            self._record(name, status)
            self._tasks.pop(name, None)
        return self._statuses.get(name, McpConnectionStatus(server=name, state="kapali"))

    def pending_task(self, name: str) -> asyncio.Task[McpConnectionStatus] | None:
        return self._tasks.get(name)

    async def logout(self, config: McpServerConfig) -> McpConnectionStatus:
        task = self._tasks.get(config.name)
        self.invalidate(config.name)
        generation = self._generations[config.name]
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        if config.url:
            storage = KeyringTokenStorage(config.url)
            async with mcp_oauth_flows().lock_for(storage.debug_identity()):
                if generation != self._generations.get(config.name, 0):
                    return self.login_status(config.name)
                await storage.clear()
        status = McpConnectionStatus(server=config.name, state="kapali", observed_at=self._clock())
        if generation == self._generations.get(config.name, 0):
            self._statuses[config.name] = status
        return status

    async def close(self) -> None:
        tasks = tuple(set(self._tasks.values()) | self._retired)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._retired.clear()

    async def _run_probe(self, config: McpServerConfig) -> McpConnectionStatus:
        return await self._probe(config)

    @staticmethod
    async def _probe_server(
        config: McpServerConfig, *, interactive: bool = True
    ) -> McpConnectionStatus:
        async with McpClient((config,), interactive=interactive) as client:
            status = client.statuses.get(config.name)
            if status is None or status.state != STATE_CONNECTED:
                return status or McpConnectionStatus(server=config.name, state="hata")
            try:
                tools = await client.list_tools(config.name)
            except Exception as error:
                return failure_status(config, error, latency_ms=status.latency_ms)
            return McpConnectionStatus(
                server=config.name,
                state=STATE_CONNECTED,
                tool_count=len(tools),
                latency_ms=status.latency_ms,
            )

    @classmethod
    async def _probe_server_quietly(cls, config: McpServerConfig) -> McpConnectionStatus:
        return await cls._probe_server(config, interactive=False)

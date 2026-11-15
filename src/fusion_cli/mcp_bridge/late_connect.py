"""Tur ortasında bağlanan MCP sunucuları ve `WaitForMcpServers` aracı (#239).

Claude Code (code.claude.com/docs/en/env-vars `MCP_CONNECTION_NONBLOCKING`,
`MCP_CONNECT_TIMEOUT_MS`; tools reference `WaitForMcpServers`): sunucular arka planda
bağlanır; bağlantısı geç biten sunucunun araçları geldiği anda kullanılabilir olur, model
de bağlanmayı süren sunucuları `WaitForMcpServers` ile bekleyebilir.

Fusion'da model isteğinin araç listesi her istekte defterden yeniden kurulur
(`engines/agent/loop.py`); bu yüzden arka plan bağlantısı bitince araçları deftere yazmak
aynı turun sıradaki isteğinde sunulmaları için yeterlidir. `WaitForMcpServers` yalnız
bağlanmayı süren sunucu varken defterdedir; hepsi bitince kaldırılır.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Iterable
from typing import Protocol

from ..config.models import McpServerConfig
from ..core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from ..tools import ToolRegistry
from .client import McpClient
from .failures import STATE_CONNECTED, STATE_LOGIN_REQUIRED
from .timeouts import startup_timeout_s
from .types import McpConnectionStatus

__all__ = ["WAIT_FOR_MCP_SERVERS", "LateConnections", "wait_summary"]

_LOG = logging.getLogger(__name__)

WAIT_FOR_MCP_SERVERS = "WaitForMcpServers"
#: Bağlantı bittikten sonra araç keşfinin (tools/list) tamamlanması için bekleme payı.
_REGISTER_GRACE_S = 10.0

_DESCRIPTION = (
    "Arka planda bağlanmayı süren MCP sunucularını bekler; bağlanan sunucunun araçları "
    "sıradaki istekten itibaren çağrılabilir. Sonuçta her sunucunun durumu yazılır. "
    "Şu an bağlanan: {names}"
)


class _Pool(Protocol):
    def connecting_tasks(self) -> dict[str, asyncio.Task[None]]: ...

    def connected_client(self, name: str) -> McpClient | None: ...

    async def refresh_catalog(self, client: McpClient) -> None: ...

    async def discard_client(self, client: McpClient) -> None: ...

    @property
    def statuses(self) -> dict[str, McpConnectionStatus]: ...


class LateConnections:
    """Arka plan bağlantısı bitince sunucunun araçlarını isteyen deftere yazar."""

    def __init__(self) -> None:
        #: (sunucu, defter kimliği) → kayıt görevi. Görev defteri canlı tutar.
        self._jobs: dict[tuple[str, int], asyncio.Task[None]] = {}

    def schedule(
        self, pool: _Pool, registry: ToolRegistry, configs: Iterable[McpServerConfig]
    ) -> None:
        """Bağlanmayı süren sunucular için kayıt görevi kur; `WaitForMcpServers`'ı yenile."""
        connecting = pool.connecting_tasks()
        loop = asyncio.get_running_loop()
        for config in configs:
            task = connecting.get(config.name)
            key = (config.name, id(registry))
            if task is None or (key in self._jobs and not self._jobs[key].done()):
                continue
            job = loop.create_task(self._register_when_ready(pool, config.name, task, registry))
            self._jobs[key] = job
            job.add_done_callback(functools.partial(self._forget, key))
        self.refresh_wait_tool(pool, registry, configs)

    def _forget(self, key: tuple[str, int], job: asyncio.Task[None]) -> None:
        if self._jobs.get(key) is job:
            del self._jobs[key]

    async def _register_when_ready(
        self, pool: _Pool, name: str, task: asyncio.Task[None], registry: ToolRegistry
    ) -> None:
        # `asyncio.wait` bekleneni iptal etmez: bu görev iptal edilse de açılış sürer.
        await asyncio.wait({task})
        client = pool.connected_client(name)
        if client is not None:
            try:
                added = await client.register_into(registry)
                await pool.refresh_catalog(client)
            except Exception as error:  # tek sunucu turu düşürmez; log'lanır
                _LOG.warning(
                    "Geç bağlanan MCP sunucusunun araçları alınamadı",
                    extra={"sunucu": name, "hata": type(error).__name__},
                )
                await pool.discard_client(client)
            else:
                _LOG.info(
                    "Geç bağlanan MCP sunucusunun araçları eklendi",
                    extra={"sunucu": name, "sayi": len(added)},
                )
        tool = registry.get(WAIT_FOR_MCP_SERVERS)
        configs = getattr(tool.run, "mcp_configs", ()) if tool is not None else ()
        self.refresh_wait_tool(pool, registry, configs)

    def pending_jobs(self, registry: ToolRegistry) -> list[asyncio.Task[None]]:
        """Deftere yazmayı süren kayıt görevleri (çağıran görevin kendisi hariç)."""
        current = asyncio.current_task()
        return [
            job
            for (_name, rid), job in self._jobs.items()
            if rid == id(registry) and job is not current and not job.done()
        ]

    def refresh_wait_tool(
        self, pool: _Pool, registry: ToolRegistry, configs: Iterable[McpServerConfig]
    ) -> None:
        """Bağlanan sunucu varken `WaitForMcpServers`'ı kaydet, yoksa kaldır."""
        wanted = tuple(configs)
        names = {config.name for config in wanted}
        connecting = sorted(name for name in pool.connecting_tasks() if name in names)
        if not connecting and not self.pending_jobs(registry):
            registry.unregister_remote(WAIT_FOR_MCP_SERVERS)
            return
        registry.register_or_replace(self._wait_tool(pool, registry, wanted, connecting))

    def _wait_tool(
        self,
        pool: _Pool,
        registry: ToolRegistry,
        configs: tuple[McpServerConfig, ...],
        connecting: list[str],
    ) -> Tool:
        async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
            del args, context
            waiting = {
                name: task
                for name, task in pool.connecting_tasks().items()
                if name in {config.name for config in configs}
            }
            if waiting:
                limit = max(startup_timeout_s(c) for c in configs if c.name in waiting)
                await asyncio.wait(waiting.values(), timeout=limit + _REGISTER_GRACE_S)
            jobs = self.pending_jobs(registry)
            if jobs:
                await asyncio.wait(jobs, timeout=_REGISTER_GRACE_S)
            names = sorted(waiting) or sorted(config.name for config in configs)
            return ToolResult(output=wait_summary(names, pool))

        _run.mcp_configs = configs  # type: ignore[attr-defined]
        return Tool(
            name=WAIT_FOR_MCP_SERVERS,
            description=_DESCRIPTION.format(names=", ".join(connecting) or "yok"),
            parameters={"type": "object", "properties": {}},
            run=_run,
            effect=ToolEffect.LOCAL,
        )

    async def cancel_all(self) -> None:
        jobs = tuple(self._jobs.values())
        self._jobs.clear()
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)


def wait_summary(names: Iterable[str], pool: _Pool) -> str:
    """Sunucu başına tek satır durum (Claude `/mcp` simgeleriyle)."""
    connecting = pool.connecting_tasks()
    statuses = pool.statuses
    lines: list[str] = []
    for name in names:
        status = statuses.get(name)
        if name in connecting:
            lines.append(f"… {name}: hâlâ bağlanıyor")
        elif status is not None and status.state == STATE_CONNECTED:
            lines.append(f"✔ {name}: bağlandı ({status.tool_count} araç)")
        elif status is not None and status.state == STATE_LOGIN_REQUIRED:
            lines.append(f"! {name}: kimlik doğrulama gerekli (/mcp)")
        else:
            detail = f" ({status.message})" if status is not None and status.message else ""
            lines.append(f"✘ {name}: bağlanamadı{detail}")
    return "\n".join(lines) or "Bağlanmayı bekleyen MCP sunucusu yok."

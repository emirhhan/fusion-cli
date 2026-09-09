"""MCP bağlantılarını arayüzlerden bağımsız yöneten durum hizmeti."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ..config.models import McpServerConfig
from .client import McpClient, McpConnectionStatus
from .tokens import KeyringTokenStorage

Probe = Callable[[McpServerConfig], Awaitable[McpConnectionStatus]]


class McpConnectionService:
    def __init__(self, *, probe: Probe | None = None) -> None:
        self._probe = probe or self._probe_server
        self._tasks: dict[str, asyncio.Task[McpConnectionStatus]] = {}
        self._statuses: dict[str, McpConnectionStatus] = {}

    async def test(self, config: McpServerConfig) -> McpConnectionStatus:
        status = await self._probe(config)
        self._statuses[config.name] = status
        return status

    def start_login(self, config: McpServerConfig) -> McpConnectionStatus:
        current = self._tasks.get(config.name)
        if current is None or current.done():
            self._tasks[config.name] = asyncio.create_task(self._run_probe(config))
        pending = McpConnectionStatus(server=config.name, state="giris_bekleniyor")
        self._statuses[config.name] = pending
        return pending

    def login_status(self, name: str) -> McpConnectionStatus:
        task = self._tasks.get(name)
        if task is not None and task.done():
            try:
                status = task.result()
            except Exception:
                status = McpConnectionStatus(
                    server=name, state="hata", message="MCP girişi tamamlanamadı."
                )
            self._statuses[name] = status
            self._tasks.pop(name, None)
        return self._statuses.get(name, McpConnectionStatus(server=name, state="kapali"))

    def pending_task(self, name: str) -> asyncio.Task[McpConnectionStatus] | None:
        return self._tasks.get(name)

    async def logout(self, config: McpServerConfig) -> McpConnectionStatus:
        task = self._tasks.pop(config.name, None)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if config.url:
            await KeyringTokenStorage(config.url).clear()
        status = McpConnectionStatus(server=config.name, state="kapali")
        self._statuses[config.name] = status
        return status

    async def close(self) -> None:
        tasks = tuple(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run_probe(self, config: McpServerConfig) -> McpConnectionStatus:
        return await self._probe(config)

    @staticmethod
    async def _probe_server(config: McpServerConfig) -> McpConnectionStatus:
        async with McpClient((config,)) as client:
            status = client.statuses.get(config.name)
            if status is None or status.state != "bagli":
                return status or McpConnectionStatus(server=config.name, state="hata")
            tools = await client.list_tools(config.name)
            return McpConnectionStatus(
                server=config.name,
                state="bagli",
                tool_count=len(tools),
                latency_ms=status.latency_ms,
            )

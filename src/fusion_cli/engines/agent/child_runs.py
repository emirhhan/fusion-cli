"""Tek parent turuna ait alt ajan iptal sahipliği."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .loop import AgentOutcome


class ChildRuns:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[AgentOutcome]] = {}

    def start(
        self,
        identifier: str,
        work: Callable[[], Coroutine[object, object, AgentOutcome]],
    ) -> asyncio.Task[AgentOutcome]:
        if identifier in self._tasks:
            raise ValueError("Alt ajan kimliği zaten kullanımda.")
        task = asyncio.create_task(work())
        self._tasks[identifier] = task
        return task

    def detach(self, identifier: str, task: asyncio.Task[AgentOutcome]) -> None:
        if self._tasks.get(identifier) is task:
            self._tasks.pop(identifier)

    async def cancel(self, identifier: str) -> bool:
        task = self._tasks.get(identifier)
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def close(self) -> None:
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

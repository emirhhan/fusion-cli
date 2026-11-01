"""Tek parent turuna ait alt ajan iptal sahipliği."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from contextvars import ContextVar, Token
from dataclasses import replace
from typing import TYPE_CHECKING

from ...core.agent_runtime_state import AgentRunState
from ...core.types import Message
from .agent_runtime_context import AgentMessageQueue

if TYPE_CHECKING:
    from .loop import AgentOutcome


MAX_AGENT_RECORDS = 128


class ChildRuns:
    def __init__(self, *, persistent: bool = False) -> None:
        self._tasks: dict[str, asyncio.Task[AgentOutcome]] = {}
        self.persistent = persistent
        self._turn_context: ContextVar[str] = ContextVar("ajan_ust_turu", default="")
        self._task_turns: dict[str, str] = {}
        self._turn_starts: dict[str, int] = {}
        #: Bu kök turda (tüm derinlikler) başlatılan alt ajan sayısı; nesne alt ajanlara
        #: aynen devredilir, bu yüzden sayaç turun toplam bütçesidir (P-035).
        self.started_total = 0
        self.session_id = uuid.uuid4().hex
        self._records: dict[str, AgentRunState] = {}
        self._histories: dict[str, tuple[Message, ...]] = {}
        self._inputs: dict[str, AgentMessageQueue] = {}
        self._background: dict[str, asyncio.Task[object]] = {}
        self._gates: dict[str, asyncio.Semaphore] = {}
        self._notifications: dict[str, list[str]] = {}
        self._writers: dict[str, Callable[[AgentRunState], Awaitable[None]]] = {}
        self._failures: list[BaseException] = []

    def start(
        self,
        identifier: str,
        work: Callable[[], Coroutine[object, object, AgentOutcome]],
    ) -> asyncio.Task[AgentOutcome]:
        if identifier in self._tasks:
            raise ValueError("Alt ajan kimliği zaten kullanımda.")
        task = asyncio.create_task(work())
        self._tasks[identifier] = task
        self.started_total += 1
        turn = self.current_turn
        self._task_turns[identifier] = turn
        if turn:
            self._turn_starts[turn] = self._turn_starts.get(turn, 0) + 1
            if len(self._turn_starts) > MAX_AGENT_RECORDS:
                inactive = next(
                    (key for key in self._turn_starts if key not in self._task_turns.values()), None
                )
                if inactive is not None:
                    self._turn_starts.pop(inactive)
        return task

    def detach(self, identifier: str, task: asyncio.Task[AgentOutcome]) -> None:
        if self._tasks.get(identifier) is task:
            self._tasks.pop(identifier)
            self._task_turns.pop(identifier, None)

    def message_queue(self, identifier: str) -> AgentMessageQueue:
        return self._inputs.setdefault(identifier, AgentMessageQueue())

    def running(self, identifier: str) -> bool:
        return any(
            task is not None and not task.done()
            for task in (self._tasks.get(identifier), self._background.get(identifier))
        )

    async def cancel(self, identifier: str) -> bool:
        task = self._background.get(identifier) or self._tasks.get(identifier)
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await self.set_status(identifier, "cancelled")
        return True

    async def close(self) -> None:
        tasks = (*self._tasks.values(), *self._background.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._background.clear()
        for identifier, state in tuple(self._records.items()):
            if state.status == "running":
                await self.set_status(identifier, "cancelled")
        self._gates.clear()
        self._notifications.clear()
        self._raise_failure()

    def remember(self, state: AgentRunState, messages: tuple[Message, ...]) -> None:
        """Tamamlanmış kayıtları sınırla; çalışan görev kaydını silme."""
        if state.agent_id not in self._records and len(self._records) >= MAX_AGENT_RECORDS:
            removable = next(
                (identifier for identifier in self._records if not self.running(identifier)), None
            )
            if removable is None:
                raise ValueError("Çalışan ajan kayıt sınırı doldu.")
            self._records.pop(removable)
            self._histories.pop(removable, None)
            self._inputs.pop(removable, None)
            self._writers.pop(removable, None)
        self._records[state.agent_id] = state
        self._histories[state.agent_id] = messages
        for identifier in tuple(self._records):
            if len(self._records) <= MAX_AGENT_RECORDS:
                break
            if identifier not in self._tasks and identifier not in self._background:
                self._records.pop(identifier, None)
                self._histories.pop(identifier, None)
                self._inputs.pop(identifier, None)

    def record(self, identifier: str) -> AgentRunState | None:
        return self._records.get(identifier)

    def records(self) -> tuple[AgentRunState, ...]:
        return tuple(self._records.values())

    def history(self, identifier: str) -> tuple[Message, ...]:
        return self._histories.get(identifier, ())

    def launch(
        self, identifier: str, work: Coroutine[object, object, object], *, max_parallel: int = 4
    ) -> None:
        """Arka plan işi mevcut sahibin denetiminde kalır."""
        previous = self._background.get(identifier)
        if previous is not None and not previous.done():
            work.close()
            raise ValueError("Ajan zaten çalışıyor.")
        state = self._records.get(identifier)
        parent = state.parent_session if state is not None else self.session_id
        gate = self._gates.setdefault(parent, asyncio.Semaphore(max(1, max_parallel)))

        async def owned() -> object:
            started = False
            try:
                async with gate:
                    started = True
                    return await work
            finally:
                if not started:
                    work.close()

        task = asyncio.create_task(owned())
        self._background[identifier] = task
        task.add_done_callback(lambda finished: self._background_done(identifier, parent, finished))

    async def drain(self) -> None:
        """Tamamlanmayı ve hataları gözle; hiçbir işi sahipsiz bırakma."""
        while self._background:
            pending = tuple(self._background.items())
            results = await asyncio.gather(*(task for _, task in pending), return_exceptions=True)
            for identifier, task in pending:
                if self._background.get(identifier) is task:
                    self._background.pop(identifier, None)

            for result in results:
                if isinstance(result, BaseException) and not isinstance(
                    result, asyncio.CancelledError
                ):
                    if result in self._failures:
                        self._failures.remove(result)
                    raise result
        self._raise_failure()

    @property
    def pending_starts(self) -> int:
        return sum(
            identifier not in self._tasks
            and not task.done()
            and (not self.persistent or self.turn_for(identifier) == self.current_turn)
            for identifier, task in self._background.items()
        )

    @property
    def current_turn(self) -> str:
        return self._turn_context.get()

    @property
    def started_for_current_turn(self) -> int:
        return (
            self._turn_starts.get(self.current_turn, 0) if self.persistent else self.started_total
        )

    def begin_turn(self, turn_id: str) -> Token[str]:
        return self._turn_context.set(turn_id)

    def end_turn(self, token: Token[str]) -> None:
        self._turn_context.reset(token)

    def turn_for(self, identifier: str) -> str:
        state = self._records.get(identifier)
        return state.parent_turn if state is not None else self._task_turns.get(identifier, "")

    async def cancel_turn(self, turn_id: str) -> None:
        if not turn_id:
            return
        for identifier in tuple(set(self._tasks) | set(self._background)):
            if self.turn_for(identifier) == turn_id:
                await self.cancel(identifier)

    def completed(self, identifier: str, text: str) -> None:
        state = self._records.get(identifier)
        if state is not None and identifier in self._background:
            notices = self._notifications.setdefault(state.parent_session, [])
            notices.append(f"{identifier}: {text[:20000]}")
            del notices[:-MAX_AGENT_RECORDS]

    async def completion_messages(self, session: str, *, wait: bool = True) -> tuple[str, ...]:
        tasks = [
            task
            for identifier, task in self._background.items()
            if (state := self._records.get(identifier)) is not None
            and state.parent_session == session
        ]
        if tasks and wait:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException) and not isinstance(
                    result, asyncio.CancelledError
                ):
                    if result in self._failures:
                        self._failures.remove(result)
                    raise result
        self._raise_failure()
        return tuple(self._notifications.pop(session, ()))

    def _background_done(self, identifier: str, parent: str, task: asyncio.Task[object]) -> None:
        if self._background.get(identifier) is task:
            self._background.pop(identifier)
        if not task.cancelled() and (failure := task.exception()) is not None:
            self._failures.append(failure)
            del self._failures[:-MAX_AGENT_RECORDS]
        if not any(
            (state := self._records.get(key)) is not None and state.parent_session == parent
            for key in self._background
        ):
            self._gates.pop(parent, None)

    def _raise_failure(self) -> None:
        if self._failures:
            raise self._failures.pop(0)

    def bind_writer(
        self, identifier: str, writer: Callable[[AgentRunState], Awaitable[None]]
    ) -> None:
        self._writers[identifier] = writer

    async def set_status(self, identifier: str, status: str) -> None:
        state = self._records.get(identifier)
        if state is None:
            return
        updated = replace(state, status=status)
        self._records[identifier] = updated
        writer = self._writers.get(identifier)
        if writer is not None:
            await writer(updated)

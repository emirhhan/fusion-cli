"""Koşan bir ekibin paylaşımlı durumu (P-061): görev alma, bitirme, posta, boşta bekleme.

Bütün üyeler aynı süreçte eşzamanlı coroutine'lerdir; pano tek `asyncio.Condition`
altında değişir (görev alma atomiktir: iki üye aynı görevi alamaz). Her değişiklik diske
yazılır ve `TeamBoardChanged` olarak yayınlanır.

Boşta bekleme (Claude Code `TeammateIdle`): koşusu biten üye, kendisine alınabilir görev
ya da okunmamış mesaj gelene veya bütün ekip boşa düşene kadar bekler. Kimse çalışmıyor
ve kimsenin işi yoksa ekip biter.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable

from ...core.events import EventPublisher
from ...core.orchestration_events import (
    TeamBoardChanged,
    TeamMemberView,
    TeamMessageView,
    TeamTaskView,
)
from .team_board import (
    BROADCAST,
    DONE,
    FAILED,
    LEAD,
    MESSAGE_CHARS,
    PENDING,
    RESULT_CHARS,
    RUNNING,
    TeamBoard,
    TeamError,
    TeamMessage,
    TeamStore,
    TeamTask,
)

#: Panoda (olayda) taşınan son mesaj sayısı ve mesaj önizlemesi.
BOARD_MESSAGES = 20
PREVIEW_CHARS = 240
#: Üye durumları.
MEMBER_WAITING, MEMBER_RUNNING, MEMBER_IDLE, MEMBER_DONE = "bekliyor", "calisiyor", "bosta", "bitti"


@dataclasses.dataclass(slots=True)
class _MemberState:
    status: str = MEMBER_WAITING
    sub_id: str = ""
    wakes: int = 0
    runs: int = 0
    last_summary: str = ""


def unread_counts(store: TeamStore, board: TeamBoard) -> dict[str, int]:
    """Önceki turlardan kalan okunmamış mesajlar (oturum açılırken bir kez, thread'de)."""
    recipients = [member.name for member in board.members] + [LEAD]
    return {
        name: max(0, len(store.inbox(board.name, name)) - board.read_count(name))
        for name in recipients
    }


class TeamSession:
    def __init__(
        self,
        store: TeamStore,
        board: TeamBoard,
        publisher: EventPublisher,
        now: Callable[[], float],
        *,
        group_size: int = 1,
        unread: dict[str, int] | None = None,
    ) -> None:
        self._store, self._publisher, self._now = store, publisher, now
        #: Alıcı → okunmamış mesaj sayısı; bellekte tutulur (bekleme koşulu dosya okumaz).
        self._unread_counts = dict(unread or {})
        self.board = board
        self.group_size = group_size
        self._condition = asyncio.Condition()
        self.members = {member.name: _MemberState() for member in board.members}
        self._recent: list[TeamMessage] = []
        self.status = "calisiyor"

    # -- görevler ---------------------------------------------------------- #

    async def claim(self, member: str, task_id: str = "") -> TeamTask:
        async with self._condition:
            candidates = [self.board.task(task_id)] if task_id else list(self.board.tasks)
            for task in candidates:
                if task is not None and self.board.is_claimable(task, member):
                    taken = dataclasses.replace(task, status=RUNNING, owner=member)
                    await self._commit(self.board.with_task(taken))
                    return taken
            raise TeamError(self._claim_refusal(member, task_id))

    def _claim_refusal(self, member: str, task_id: str) -> str:
        task = self.board.task(task_id) if task_id else None
        if task_id and task is None:
            return f"'{task_id}' kimlikli görev yok."
        if task is not None and task.status != PENDING:
            return f"{task.id} zaten {task.status} ({task.owner or '-'})."
        if task is not None and task.assignee not in {"", member}:
            return f"{task.id} {task.assignee} üyesine atanmış."
        if task is not None:
            return f"{task.id} bağımlılıkları bitmedi: {', '.join(task.depends_on)}."
        return "Şu an alabileceğin görev yok; bekleyen görevlerin bağımlılıkları sürüyor."

    async def finish(self, member: str, task_id: str, result: str, *, ok: bool) -> TeamTask:
        async with self._condition:
            task = self.board.task(task_id)
            if task is None:
                raise TeamError(f"'{task_id}' kimlikli görev yok.")
            if task.owner != member or task.status != RUNNING:
                raise TeamError(
                    f"{task_id} senin üzerinde değil "
                    f"(durum {task.status}, sahip {task.owner or '-'})."
                )
            done = dataclasses.replace(
                task, status=DONE if ok else FAILED, result=result[:RESULT_CHARS]
            )
            await self._commit(self.board.with_task(done))
            return done

    async def add_task(
        self,
        creator: str,
        title: str,
        *,
        description: str = "",
        depends_on: tuple[str, ...] = (),
        assignee: str = "",
    ) -> TeamTask:
        async with self._condition:
            return await self._add_locked(creator, title, description, depends_on, assignee)

    async def _add_locked(
        self, creator: str, title: str, description: str, depends_on: tuple[str, ...], assignee: str
    ) -> TeamTask:
        if not title.strip():
            raise TeamError("Görevin başlığı boş olamaz.")
        unknown = [dep for dep in depends_on if self.board.task(dep) is None]
        if unknown:
            raise TeamError(f"Bilinmeyen bağımlılık: {', '.join(unknown)}.")
        if assignee and self.board.member(assignee) is None:
            raise TeamError(f"'{assignee}' ekipte yok.")
        task = TeamTask(
            id=self.board.next_task_id(),
            title=title.strip()[:200],
            description=description.strip()[:RESULT_CHARS],
            depends_on=depends_on,
            assignee=assignee,
            created_by=creator,
        )
        await self._commit(self.board.with_task(task))
        return task

    # -- posta ------------------------------------------------------------- #

    async def send(self, sender: str, recipient: str, text: str) -> tuple[str, ...]:
        if not text.strip():
            raise TeamError("Boş mesaj gönderilmez.")
        names = [member.name for member in self.board.members]
        if recipient == BROADCAST:
            targets = tuple(name for name in names if name != sender)
        elif recipient == LEAD or recipient in names:
            targets = (recipient,)
        else:
            raise TeamError(
                f"'{recipient}' ekipte yok (üyeler: {', '.join(names)}, lider, herkes)."
            )
        async with self._condition:
            for target in targets:
                message = TeamMessage(sender, target, text.strip()[:MESSAGE_CHARS], self._now())
                await asyncio.to_thread(self._store.append, self.board.name, message)
                self._unread_counts[target] = self._unread_counts.get(target, 0) + 1
                self._recent = [*self._recent, message][-BOARD_MESSAGES:]
            self._condition.notify_all()
            self._publish()
        return targets

    async def take_inbox(self, recipient: str) -> list[TeamMessage]:
        """Okunmamış mesajlar (okundu işaretlenir)."""
        async with self._condition:
            messages = await asyncio.to_thread(self._store.inbox, self.board.name, recipient)
            unread = messages[self.board.read_count(recipient) :]
            self._unread_counts[recipient] = 0
            if unread:
                await self._commit(self.board.with_read_count(recipient, len(messages)))
            return unread

    def _unread(self, recipient: str) -> int:
        return self._unread_counts.get(recipient, 0)

    # -- üye yaşam döngüsü ------------------------------------------------- #

    async def member_started(self, member: str) -> None:
        async with self._condition:
            self.members[member].status = MEMBER_RUNNING
            self.members[member].runs += 1
            self._publish()

    async def member_idle(self, member: str, *, sub_id: str, summary: str) -> tuple[str, ...]:
        """Koşu bitti: üzerinde kalan görevler panoya geri bırakılır (kimliklerini döndürür)."""
        async with self._condition:
            state = self.members[member]
            state.status, state.sub_id, state.last_summary = MEMBER_IDLE, sub_id, summary
            released = tuple(
                task.id
                for task in self.board.tasks
                if task.owner == member and task.status == RUNNING
            )
            board = self.board
            for task_id in released:
                task = board.task(task_id)
                if task is not None:
                    board = board.with_task(dataclasses.replace(task, status=PENDING, owner=""))
            await self._commit(board)
            return released

    async def wait_for_work(self, member: str) -> bool:
        """Üyeye iş gelene (True) ya da bütün ekip boşa düşene (False) kadar bekle."""
        async with self._condition:
            await self._condition.wait_for(lambda: self._has_work(member) or self._all_idle())
            return self._has_work(member)

    async def member_done(self, member: str) -> None:
        async with self._condition:
            self.members[member].status = MEMBER_DONE
            self._condition.notify_all()
            self._publish()

    async def wake(self, member: str) -> None:
        async with self._condition:
            self.members[member].wakes += 1

    def has_work(self, member: str) -> bool:
        return self._has_work(member)

    def _has_work(self, member: str) -> bool:
        if any(self.board.is_claimable(task, member) for task in self.board.tasks):
            return True
        return self._unread(member) > 0

    def _all_idle(self) -> bool:
        return all(state.status in {MEMBER_IDLE, MEMBER_DONE} for state in self.members.values())

    # -- yayın ------------------------------------------------------------- #

    async def _commit(self, board: TeamBoard) -> None:
        self.board = dataclasses.replace(board, updated_at=self._now())
        await asyncio.to_thread(self._store.save, self.board)
        self._condition.notify_all()
        self._publish()

    async def close(self, status: str) -> None:
        async with self._condition:
            self.status = status
            self._publish()

    def _publish(self) -> None:
        self._publisher.publish(
            TeamBoardChanged(
                team=self.board.name,
                goal=self.board.goal,
                status=self.status,
                tasks=tuple(
                    TeamTaskView(
                        task.id,
                        task.title,
                        task.status,
                        task.owner,
                        task.depends_on,
                        _preview(task.result),
                    )
                    for task in self.board.tasks
                ),
                members=tuple(
                    TeamMemberView(
                        member.name, member.persona, state.status, state.sub_id, state.wakes
                    )
                    for member in self.board.members
                    if (state := self.members.get(member.name)) is not None
                ),
                messages=tuple(
                    TeamMessageView(
                        message.sender, message.recipient, _preview(message.text), message.at
                    )
                    for message in self._recent
                ),
                group_size=self.group_size,
            )
        )


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= PREVIEW_CHARS else flat[: PREVIEW_CHARS - 1] + "…"

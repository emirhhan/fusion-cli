"""Ekip kanca kapıları (P-061 + P-009): `TaskCreated`, `TaskCompleted`, `TeammateIdle`.

Claude Code ajan ekiplerinin kalite kapılarıyla aynı sözleşme (olay adları ve yük birebir):

    TaskCreated     görev panoya eklenmeden önce; çıkış 2 → görev eklenmez, gerekçe
                    ekleyene (üye ya da lider) araç hatası olarak döner
    TaskCompleted   üye görevi "tamam" yapmadan önce; çıkış 2 → görev üyede kalır,
                    gerekçe üyeye geri bildirim olur
    TeammateIdle    üyenin koşusu bitip boşa düşmeden önce; çıkış 2 → üye gerekçeyle
                    yeniden koşar (uyanma tavanı `runtime.agent_team_max_wakes` sayılır)

Yük: `team_name`, `teammate_name` (lider eklediyse yazılmaz); görev olaylarında `task_id`,
`task_subject`, `task_description`. Eşleştirici yoktur. `continue: false` üyeyi durdurur:
o koşu kısa özetle biter ve üye yeniden uyandırılmaz.

Kanca oturumu yoksa (`deps.hooks` boş) her kapı açıktır; süreç açılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.events import EventPublisher
from ...core.hooks.events import HookEvent
from ...ui import messages
from ..hooks.session import HookSession
from .hook_bridge import publish_verdict
from .team_board import LEAD, TeamTask


@dataclass(frozen=True, slots=True)
class TeamGate:
    """Kapı kararı: engel gerekçesi ve/veya üyeyi durdurma metni (`None` = açık)."""

    blocked: str | None = None
    halt: str | None = None

    @property
    def is_open(self) -> bool:
        return self.blocked is None and self.halt is None

    def creation_refusal(self) -> str:
        """`TaskCreated` engelinde ekleyene dönen metin."""
        return self.halt or messages.HOOKS_TASK_CREATE_BLOCKED.format(reason=self.blocked)

    def completion_refusal(self, task_id: str) -> str:
        """`TaskCompleted` engelinde üyeye dönen geri bildirim."""
        return self.halt or messages.HOOKS_TASK_COMPLETE_BLOCKED.format(
            task=task_id, reason=self.blocked
        )

    def idle_prompt(self) -> str:
        """`TeammateIdle` engelinde üyenin yeniden koşacağı istem."""
        return messages.HOOKS_TEAMMATE_CONTINUE.format(reason=self.blocked)


OPEN_GATE = TeamGate()


class TeamHooks:
    """Bir ekip koşusunun kanca kapıları."""

    def __init__(self, session: HookSession | None, publisher: EventPublisher, team: str) -> None:
        self._session, self._publisher, self._team = session, publisher, team

    async def task_created(self, task: TeamTask, creator: str) -> TeamGate:
        return await self._gate(HookEvent.TASK_CREATED, creator, task)

    async def task_completed(self, task: TeamTask, member: str) -> TeamGate:
        return await self._gate(HookEvent.TASK_COMPLETED, member, task)

    async def teammate_idle(self, member: str) -> TeamGate:
        return await self._gate(HookEvent.TEAMMATE_IDLE, member)

    async def _gate(self, event: HookEvent, member: str, task: TeamTask | None = None) -> TeamGate:
        if self._session is None:
            return OPEN_GATE
        fields: dict[str, object] = {"team_name": self._team}
        if member and member != LEAD:
            fields["teammate_name"] = member
        if task is not None:
            fields |= {
                "task_id": task.id,
                "task_subject": task.title,
                "task_description": task.description,
            }
        verdict = await self._session.emit(event, fields=fields)
        publish_verdict(self._publisher, verdict)
        halt = None
        if verdict.halt:
            reason = verdict.stop_reason or verdict.reason or messages.HOOKS_NO_REASON
            halt = messages.HOOKS_TEAMMATE_HALTED.format(event=event.value, reason=reason)
        blocked = (verdict.reason or messages.HOOKS_NO_REASON) if verdict.blocked else None
        return TeamGate(blocked, halt)

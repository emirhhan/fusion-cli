"""Ajan ekibi çalışma zamanı (P-061): lider (ana ajan) + eşzamanlı üyeler.

Lider `team_run` ile ekibi kurar ya da sürdürür: hedef, üyeler, görevler ve üyelere
mesajlar. Her üye `team.run_subagent` ile koşan bir alt ajandır; panoya yalnız üye
araçlarıyla (`team_board`, `team_task`, `team_send`) dokunur. Koşusu biten üye boşta
bekler; kendisine alınabilir görev ya da mesaj gelirse yeniden uyandırılır
(`runtime.agent_team_max_wakes`). Kimse çalışmıyor ve kimsenin işi yoksa ekip biter;
lider panonun son hâlini, lidere gelen mesajları ve üye özetlerini rapor olarak alır.

Pano dosyada kalır: aynı adla yeniden çağrılan `team_run` kaldığı yerden sürer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.clock import SystemClock
from ...core.errors import PathAccessError
from .hook_bridge import session_of
from .orchestration_runs import (
    BudgetedRuns,
    ScopeGate,
    gate_scope,
    orchestration_deps,
    registry_with,
    turn_budget_refusal,
    turn_remaining,
)
from .team import RunAgent, SubRun, SubTask, run_subagent
from .team_board import (
    DONE,
    LEAD,
    PENDING,
    RUNNING,
    TeamBoard,
    TeamError,
    TeamMember,
    TeamMessage,
    TeamStore,
    TeamTask,
    check_name,
    resolve_dependencies,
)
from .team_hooks import TeamHooks
from .team_policy import cap_report
from .team_scope import derive_sub_context
from .team_session import TeamSession, unread_counts
from .team_tools_member import member_tools

if TYPE_CHECKING:
    from .loop import AgentDeps

_LOG = logging.getLogger(__name__)

#: Yapılandırma okunamazsa kullanılan yedek tavanlar.
DEFAULT_MAX_MEMBERS = 5
DEFAULT_MAX_WAKES = 3
DEFAULT_MAX_RUNS = 16
#: Raporda görev sonucunun ve üye özetinin en fazla karakteri.
REPORT_RESULT_CHARS = 600

FIRST_PROMPT = "Ekip işine başla: team_board ile panoya bak, team_task ile görev al ve bitir."
WAKE_PROMPT = "Yeniden uyandırıldın: panoda {reasons}. team_board ile bak ve kurala göre devam et."


@dataclass(frozen=True, slots=True)
class NewTask:
    title: str
    description: str = ""
    #: Kimlik ("g2") ya da aynı çağrıdaki başka görevin başlığı.
    depends_on: tuple[str, ...] = ()
    assignee: str = ""


@dataclass(frozen=True, slots=True)
class TeamRequest:
    name: str
    goal: str = ""
    members: tuple[TeamMember, ...] = ()
    tasks: tuple[NewTask, ...] = ()
    #: (alıcı, metin): liderin üyelere mesajları.
    messages: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class TeamLimits:
    max_members: int
    max_wakes: int
    max_runs: int


@dataclass(frozen=True, slots=True)
class TeamResult:
    status: str
    report: str
    runs: int
    #: Ekibi beklenmedik biçimde durduran hata (boşsa ekip olağan yoldan bitti).
    error: str = ""


def team_limits(deps: AgentDeps) -> TeamLimits:
    runtime = deps.config.runtime
    return TeamLimits(
        max_members=max(1, int(getattr(runtime, "agent_team_max_members", DEFAULT_MAX_MEMBERS))),
        max_wakes=max(0, int(getattr(runtime, "agent_team_max_wakes", DEFAULT_MAX_WAKES))),
        max_runs=max(1, int(getattr(runtime, "agent_team_max_runs", DEFAULT_MAX_RUNS))),
    )


@cache
def _member_prompt_template() -> str:
    return (Path(__file__).parent / "prompts" / "team_member.md").read_text(encoding="utf-8")


def prepare_board(
    existing: TeamBoard | None, request: TeamRequest, limits: TeamLimits, now: float
) -> TeamBoard:
    """Yeni ekip kur ya da var olanı sürdür (yarım kalmış görevler panoya döner)."""
    if existing is None and (not request.goal.strip() or not request.members or not request.tasks):
        raise TeamError("Yeni ekip için 'hedef', 'uyeler' ve en az bir 'gorevler' gerekli.")
    members = request.members or (existing.members if existing is not None else ())
    if len(members) > limits.max_members:
        raise TeamError(
            f"Ekip en fazla {limits.max_members} üye alır (runtime.agent_team_max_members)."
        )
    names = [member.name for member in members]
    if len(set(names)) != len(names):
        raise TeamError("Üye adları benzersiz olmalı.")
    if existing is None:
        return TeamBoard(
            request.name, request.goal.strip(), members, created_at=now, updated_at=now
        )
    stale = tuple(
        replace(task, status=PENDING, owner="") if task.status == RUNNING else task
        for task in existing.tasks
    )
    return replace(
        existing, goal=request.goal.strip() or existing.goal, members=members, tasks=stale
    )


class TeamRun:
    def __init__(
        self,
        deps: AgentDeps,
        session: TeamSession,
        *,
        depth: int,
        run_agent: RunAgent,
        limits: TeamLimits,
    ) -> None:
        self._deps, self._session, self._depth = deps, session, depth
        self._run_agent, self._limits = run_agent, limits
        self._runs = BudgetedRuns(deps.child_runs)
        # Üyeler de iş akışıyla AYNI yazma alanı kuralına uyar (`ScopeGate`). Ölçüldü
        # (31 Ekim): alanı belirsiz iki yazar üye (`kod`, `test`) aynı anda koşuyordu.
        self._gate = ScopeGate()

    async def execute(self) -> TeamResult:
        board = self._session.board
        error = ""
        try:
            async with asyncio.TaskGroup() as group:
                for member in board.members:
                    group.create_task(self._member_loop(member))
        except asyncio.CancelledError:
            await self._runs.close()
            await self._session.close("durdu")
            raise
        except Exception as failure:  # pano 'calisiyor' kalmasın
            # Ölçüldü (31 Ekim): üye döngüsündeki bir istisna `session.close` çağrılmadan
            # yukarı çıkıyor, pano masaüstünde sonsuza dek "Çalışıyor" kalıyordu.
            _LOG.exception("ekip beklenmedik hatayla durdu", extra={"ekip": board.name})
            error = _failure_text(failure)
        finally:
            await self._runs.close()
        final = self._session.board
        done = final.tasks and all(task.status == DONE for task in final.tasks)
        status = "bitti" if done and not error else "durdu"
        await self._session.close(status)
        try:
            lead_mail = await self._session.take_inbox(LEAD)
        except OSError as failure:
            error = error or _failure_text(failure)
            lead_mail = []
        report = self._report(status, lead_mail)
        if error:
            report = f"Ekip beklenmedik hatayla durdu: {error}\n\n{report}"
        return TeamResult(status, report, self._runs.started_total, error)

    async def _member_loop(self, member: TeamMember) -> None:
        session, name = self._session, member.name
        registry = registry_with(self._deps.base_registry, member_tools(session, name))
        member_deps = orchestration_deps(
            self._deps, self._runs, agent_limit=self._limits.max_runs, registry=registry
        )
        # `TeammateIdle` engelinde üyenin boşa düşmeden yeniden koşacağı istem.
        feedback: str | None = None
        last: SubRun | None = None
        try:
            while True:
                if feedback is None and not session.has_work(name):
                    await session.member_idle(
                        name,
                        sub_id=session.members[name].sub_id,
                        summary=session.members[name].last_summary,
                    )
                    if not await session.wait_for_work(name):
                        break
                state = session.members[name]
                if (
                    state.runs > self._limits.max_wakes
                    or self._runs.started_total >= self._limits.max_runs
                ):
                    if last is not None and feedback is not None:
                        # TeammateIdle engeli tavana takıldı: üzerindeki görevler panoya döner.
                        await session.member_idle(name, sub_id=last.sub_id, summary=last.text)
                    break
                prompt = feedback or (FIRST_PROMPT if state.runs == 0 else self._wake_prompt(name))
                if state.runs:
                    await session.wake(name)
                run = last = await self._run_member(member, member_deps, prompt)
                feedback = None
                if run.status not in {"budget", "cancelled"} and name not in session.halted:
                    gate = await session.hooks.teammate_idle(name)
                    if gate.halt is not None:
                        session.halted.add(name)
                    elif gate.blocked is not None:
                        feedback = gate.idle_prompt()
                        continue
                await session.member_idle(name, sub_id=run.sub_id, summary=run.text)
                if run.status in {"budget", "cancelled"} or name in session.halted:
                    break
        finally:
            await session.member_done(name)

    async def _run_member(self, member: TeamMember, member_deps: AgentDeps, prompt: str) -> SubRun:
        """Üyenin tek koşusu: yazma alanı kapısını bekler ("sırada"), sonra koşar."""
        session = self._session
        subtask = self._subtask(member, prompt)
        # "sırada": kapıyı bekleyen üye boşta sayılmaz (ekip erken bitmesin).
        await session.member_queued(member.name)
        async with self._gate.hold(self._gate_key(subtask)):
            await session.member_started(member.name)
            return await run_subagent(
                member_deps,
                subtask,
                depth=self._depth,
                run_agent=self._run_agent,
                group_size=session.group_size,
            )

    def _gate_key(self, subtask: SubTask) -> tuple[Path, ...] | None:
        """Salt okur ve çalışma ağacındaki üye `()`, alanı bilinen yazar alanı, kalan `None`."""
        if subtask.isolation == "worktree":
            return ()
        try:
            scope = derive_sub_context(self._deps.tool_context, subtask).write_scope
        except PathAccessError:
            # Geçersiz alanı `run_subagent` reddedip açıklar; o arada kimseyle koşmasın.
            scope = None
        return gate_scope(subtask.read_only, scope)

    def _subtask(self, member: TeamMember, prompt: str) -> SubTask:
        board = self._session.board
        roster = "\n".join(
            f"- {item.name}"
            + (f" ({item.persona})" if item.persona else "")
            + (" — salt okur" if item.read_only else "")
            + (f" — yazma alanı: {', '.join(item.write_scope)}" if item.write_scope else "")
            for item in board.members
        )
        brief = _member_prompt_template().format(
            team=board.name, member=member.name, goal=board.goal, roster=roster
        )
        return SubTask(
            task=prompt,
            persona=member.persona,
            read_only=member.read_only,
            write_scope=member.write_scope,
            isolation=member.isolation,
            brief=brief,
        )

    def _wake_prompt(self, name: str) -> str:
        board = self._session.board
        claimable = [task.id for task in board.tasks if board.is_claimable(task, name)]
        reasons = []
        if claimable:
            reasons.append(f"alabileceğin görevler var ({', '.join(claimable[:6])})")
        if not claimable or self._session.has_work(name):
            reasons.append("sana gelen mesaj olabilir")
        return WAKE_PROMPT.format(reasons=" ve ".join(reasons))

    def _report(self, status: str, lead_mail: list[TeamMessage]) -> str:
        board = self._session.board
        done = sum(task.status == DONE for task in board.tasks)
        lines = [
            f"Ekip '{board.name}': {status} — {done}/{len(board.tasks)} görev tamam, "
            f"{self._runs.started_total} üye koşusu.",
            "",
            "## Görevler",
        ]
        lines.extend(_task_line(board, task) for task in board.tasks)
        if lead_mail:
            lines.extend(("", "## Lidere gelen mesajlar"))
            lines.extend(f"- {message.sender}: {message.text}" for message in lead_mail)
        lines.extend(("", "## Üyeler"))
        for member in board.members:
            state = self._session.members[member.name]
            summary = " ".join(state.last_summary.split())[:REPORT_RESULT_CHARS]
            lines.append(
                f"- {member.name}: {state.runs} koşu" + (f" — {summary}" if summary else "")
            )
        return cap_report("\n".join(lines))


def _failure_text(failure: BaseException) -> str:
    """İstisna (ya da TaskGroup'un ExceptionGroup'u) için tek satırlık açıklama."""
    while isinstance(failure, BaseExceptionGroup) and failure.exceptions:
        failure = failure.exceptions[0]
    return f"{type(failure).__name__}: {failure}"


def _task_line(board: TeamBoard, task: TeamTask) -> str:
    owner = f" ({task.owner})" if task.owner else ""
    blocked = " — engellendi: bağımlılığı başarısız" if board.is_blocked(task) else ""
    result = " ".join(task.result.split())[:REPORT_RESULT_CHARS]
    return f"- {task.id} {task.status}{owner}: {task.title}{blocked}" + (
        f" → {result}" if result else ""
    )


async def run_agent_team(
    deps: AgentDeps,
    request: TeamRequest,
    *,
    depth: int,
    run_agent: RunAgent,
    store: TeamStore,
) -> TeamResult:
    """Panoyu hazırla, liderin görev/mesajlarını işle ve üyeleri koştur."""
    check_name(request.name)
    limits = team_limits(deps)
    # Tur geneli tavan: kalan pay üye koşusu tavanını daraltır, hiç pay yoksa başlamaz.
    remaining, _ = turn_remaining(deps)
    if remaining < 1:
        raise TeamError(turn_budget_refusal(deps, 1) or "")
    limits = replace(limits, max_runs=min(limits.max_runs, remaining))
    clock = deps.budget.clock if deps.budget is not None else SystemClock()
    existing = await asyncio.to_thread(store.load, request.name)
    board = prepare_board(existing, request, limits, clock.now())
    unread = await asyncio.to_thread(unread_counts, store, board)
    session = TeamSession(
        store,
        board,
        deps.publisher,
        clock.now,
        group_size=limits.max_runs,
        unread=unread,
        hooks=TeamHooks(session_of(deps), deps.publisher, board.name),
    )
    created: dict[str, str] = {}
    for task in request.tasks:
        added = await session.add_task(
            LEAD,
            task.title,
            description=task.description,
            depends_on=resolve_dependencies(session.board, created, task.depends_on),
            assignee=task.assignee,
        )
        created[task.title.strip()] = added.id
    for recipient, text in request.messages:
        await session.send(LEAD, recipient, text)
    if not any(session.has_work(member.name) for member in session.board.members):
        await session.close("durdu")
        return TeamResult(
            "durdu",
            f"Ekip '{request.name}': üyelerin alabileceği görev ya da okunmamış mesaj yok.",
            0,
        )
    return await TeamRun(deps, session, depth=depth, run_agent=run_agent, limits=limits).execute()

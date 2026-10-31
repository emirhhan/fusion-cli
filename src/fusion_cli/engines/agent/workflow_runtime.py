"""Dinamik iş akışı çalışma zamanı (P-062).

Açılmış planı (`workflow_plan`) yürütür: her ajan düğümü `team.run_subagent` ile koşar
(kişilik, araç süzgeci, yazma alanı, worktree, kart olayları aynen), paralel düğümler
eşzamanlılık tavanı ve yazma alanı kapısı altında koşar, sıra düğümleri `{onceki}`
ile çıktıyı bir sonrakine geçirir.

Bütçe: koşunun kendi ajan tavanı vardır (`runtime.dynamic_workflow_max_agents`, tanımdaki
`en_fazla_ajan` yalnız daraltır); plan bunu aşarsa hiç başlamaz. İptal üç yoldan gelir:
tur iptali (Ctrl+C / masaüstünde Durdur), tek ajanın kartındaki Durdur ve `/workflows iptal`
(`.iptal` işaret dosyası; başka terminalden de verilebilir). Her durum değişikliği
`WorkflowProgress` olayı ve koşu kaydı olarak yazılır.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.clock import SystemClock
from ...core.errors import PathAccessError
from ...core.orchestration_events import WorkflowNodeView, WorkflowProgress
from .orchestration_runs import BudgetedRuns, ScopeGate, gate_scope, orchestration_deps
from .team import RunAgent, SubTask, run_subagent
from .team_policy import cap_report
from .team_scope import derive_sub_context
from .workflow_plan import BoundInputs, PlanAgent, PlanGroup, PlanNode, agents_in, render_prompt
from .workflow_spec import WorkflowError, WorkflowSpec
from .workflow_store import RunRecord, WorkflowStore

if TYPE_CHECKING:
    from .loop import AgentDeps

_LOG = logging.getLogger(__name__)

#: Yapılandırma okunamazsa (eski config) kullanılan yedek tavanlar.
DEFAULT_MAX_AGENTS = 50
#: İptal işaret dosyasının yoklanma aralığı (saniye).
CANCEL_POLL_S = 0.5
_STATUS = {"cancelled": "iptal"}
SKIPPED_SUMMARY = "Boru hattında önceki adım başarısız; atlandı."


@dataclass(frozen=True, slots=True)
class WorkflowLimits:
    max_agents: int
    concurrency: int


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    run_id: str
    status: str
    agents: int
    report: str


def workflow_limits(deps: AgentDeps, spec: WorkflowSpec) -> WorkflowLimits:
    """Yapılandırma tavanı; tanım yalnız daraltabilir."""
    runtime = deps.config.runtime
    ceiling = max(1, int(getattr(runtime, "dynamic_workflow_max_agents", DEFAULT_MAX_AGENTS)))
    parallel = int(getattr(runtime, "dynamic_workflow_max_concurrent", 0) or 0)
    parallel = max(1, parallel or runtime.max_parallel_agents)
    return WorkflowLimits(
        max_agents=min(spec.max_agents or ceiling, ceiling),
        concurrency=min(spec.concurrency or parallel, parallel),
    )


def check_plan(plan: PlanGroup, limits: WorkflowLimits) -> int:
    """Plandaki ajan sayısı; tavanı aşarsa koşu başlamadan reddedilir."""
    count = len(agents_in(plan))
    if count > limits.max_agents:
        raise WorkflowError(
            f"Bu iş akışı {count} ajan başlatacak; tavan {limits.max_agents} "
            "(runtime.dynamic_workflow_max_agents). Tanımı küçült ya da tavanı yükselt."
        )
    return count


class WorkflowRun:
    """Tek bir koşunun durumu ve yürütücüsü."""

    def __init__(
        self,
        deps: AgentDeps,
        spec: WorkflowSpec,
        plan: PlanGroup,
        inputs: BoundInputs,
        *,
        depth: int,
        run_agent: RunAgent,
        store: WorkflowStore,
        limits: WorkflowLimits,
    ) -> None:
        self.run_id = uuid.uuid4().hex[:12]
        self._deps, self._spec, self._plan, self._inputs = deps, spec, plan, inputs
        self._depth, self._run_agent, self._store, self._limits = depth, run_agent, store, limits
        self._runs = BudgetedRuns(deps.child_runs)
        self._member = orchestration_deps(deps, self._runs, agent_limit=limits.max_agents)
        self._semaphore = asyncio.Semaphore(limits.concurrency)
        self._gate = ScopeGate()
        self._clock = deps.budget.clock if deps.budget is not None else SystemClock()
        self._started = self._clock.now()
        self._results: dict[str, str] = {}
        self._nodes = {
            agent.key: WorkflowNodeView(agent.key, agent.label, "bekliyor", phase=agent.phase)
            for agent in agents_in(plan)
        }
        self._phase = ""
        self._status = "calisiyor"
        self._message = ""
        self._flag_cancelled = False

    async def execute(self) -> WorkflowResult:
        await self._publish()
        work = asyncio.create_task(self._node(self._plan, ""))
        watcher = asyncio.create_task(self._watch(work))
        output = ""
        try:
            output, _ = await work
            failed = any(node.status != "tamam" for node in self._nodes.values())
            self._status = "yarim" if failed else "tamam"
        except asyncio.CancelledError:
            self._status = "iptal"
            self._message = "İptal istendi." if self._flag_cancelled else "Tur iptal edildi."
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                await self._finish("")
                raise
        except Exception as error:  # kayıt ve pano 'calisiyor' kalmasın
            # Ölçüldü (31 Ekim): yalnız CancelledError yakalanıyordu; başka bir istisnada
            # `_finish` çağrılmadan çıkılıyor, kayıt canlı pid ile 'calisiyor' kalıyordu.
            _LOG.exception("iş akışı koşusu beklenmedik hatayla durdu", extra={"kosu": self.run_id})
            self._status = "hata"
            self._message = f"Beklenmedik hata: {type(error).__name__}: {error}"
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            await self._runs.close()
        report = self._report(output)
        await self._finish(report)
        return WorkflowResult(self.run_id, self._status, self._runs.started_total, report)

    async def _watch(self, work: asyncio.Task[tuple[str, bool]]) -> None:
        while not work.done():
            await asyncio.sleep(CANCEL_POLL_S)
            if await asyncio.to_thread(self._store.cancel_requested, self.run_id):
                self._flag_cancelled = True
                work.cancel()
                return

    async def _node(self, node: PlanNode, previous: str) -> tuple[str, bool]:
        """Düğümün çıktısı ve kullanılabilir olup olmadığı.

        Boru hattında (`sira`) kullanılamayan çıktıdan sonra kalan adımlar `atlandi` olur.
        Ölçüldü (31 Ekim): başarısız ajanın hata metni `{onceki}` olarak sonrakine
        veriliyor, zincirin geri kalanı boşa token harcıyordu. Paralel düğüm, kollarından
        biri bile başarılıysa kullanılabilir sayılır (kısmi sonuçla devam edilir).
        """
        if isinstance(node, PlanAgent):
            return await self._agent(node, previous)
        if not node.parallel:
            output, usable = previous, True
            for child in node.children:
                if not usable:
                    await self._skip(child)
                    continue
                output, usable = await self._node(child, output)
            joined = output
        else:
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(self._node(child, previous)) for child in node.children]
            joined = "\n\n".join(
                f"### {self._child_label(node, index, child)}\n{task.result()[0]}"
                for index, (child, task) in enumerate(zip(node.children, tasks, strict=True))
            )
            usable = any(task.result()[1] for task in tasks) or not tasks
        if node.result_id:
            self._results[node.result_id] = joined
        return joined, usable

    async def _skip(self, node: PlanNode) -> None:
        for agent in agents_in(node):
            current = self._nodes[agent.key]
            self._nodes[agent.key] = dataclasses.replace(
                current, status="atlandi", summary=SKIPPED_SUMMARY
            )
        await self._publish()

    @staticmethod
    def _child_label(group: PlanGroup, index: int, child: PlanNode) -> str:
        if index < len(group.item_labels):
            return group.item_labels[index]
        return child.label if isinstance(child, PlanAgent) else str(index + 1)

    async def _agent(self, node: PlanAgent, previous: str) -> tuple[str, bool]:
        prompt = render_prompt(
            node.prompt, inputs=self._inputs, results=self._results, previous=previous
        )
        options = node.options
        subtask = SubTask(
            task=prompt,
            persona=options.persona,
            read_only=options.read_only,
            write_scope=options.write_scope,
            isolation=options.isolation,
        )
        try:
            scope = derive_sub_context(self._deps.tool_context, subtask).write_scope
        except PathAccessError as error:
            await self._mark(node.key, "basarisiz", summary=f"Yazma alanı geçersiz: {error}")
            return "", False
        async with self._gate.hold(gate_scope(options.read_only, scope)), self._semaphore:
            self._phase = node.phase or self._phase
            await self._mark(node.key, "calisiyor")
            # `group_size` = plandaki ajan sayısı: masaüstü bu koşunun kartlarını panosuyla
            # aynı mesajda toplar (bkz. app/src/team/orkestrasyon.ts).
            run = await run_subagent(
                self._member,
                subtask,
                depth=self._depth,
                run_agent=self._run_agent,
                group_size=len(self._nodes),
            )
        status = "tamam" if run.ok else _STATUS.get(run.status, "basarisiz")
        await self._mark(node.key, status, sub_id=run.sub_id, summary=run.text)
        if node.result_id:
            self._results[node.result_id] = run.text
        return run.text, status == "tamam"

    async def _mark(self, key: str, status: str, *, sub_id: str = "", summary: str = "") -> None:
        current = self._nodes[key]
        self._nodes[key] = dataclasses.replace(
            current,
            status=status,
            sub_id=sub_id or current.sub_id,
            summary=_one_line(summary) if summary else current.summary,
        )
        await self._publish()

    async def _publish(self) -> None:
        elapsed = round(self._clock.now() - self._started, 1)
        nodes = tuple(self._nodes.values())
        self._deps.publisher.publish(
            WorkflowProgress(
                run_id=self.run_id,
                name=self._spec.name,
                status=self._status,
                phase=self._phase,
                agents_started=self._runs.started_total,
                agents_limit=self._limits.max_agents,
                nodes=nodes,
                elapsed_s=elapsed,
                message=self._message,
            )
        )
        await self._write(self._record(nodes, report=""))

    async def _write(self, record: RunRecord) -> None:
        """Koşu kaydını yaz; disk hatası koşuyu düşürmez (pano olayı zaten yayınlandı)."""
        try:
            await asyncio.to_thread(self._store.write_run, record)
        except OSError as error:
            _LOG.warning(
                "iş akışı koşu kaydı yazılamadı",
                extra={"kosu": self.run_id, "hata": str(error)},
            )

    def _record(self, nodes: tuple[WorkflowNodeView, ...], *, report: str) -> RunRecord:
        finished = self._status != "calisiyor"
        return RunRecord(
            run_id=self.run_id,
            name=self._spec.name,
            status=self._status,
            started_at=self._started,
            finished_at=self._clock.now() if finished else 0.0,
            phase=self._phase,
            agents_started=self._runs.started_total,
            agents_limit=self._limits.max_agents,
            nodes=nodes,
            message=self._message,
            pid=os.getpid(),
            report=report,
        )

    async def _finish(self, report: str) -> None:
        for key, node in tuple(self._nodes.items()):
            if node.status in {"bekliyor", "calisiyor"}:
                self._nodes[key] = dataclasses.replace(
                    node, status="iptal" if node.status == "calisiyor" else "atlandi"
                )
        await self._publish()
        if report:
            await self._write(self._record(tuple(self._nodes.values()), report=report))

    def _report(self, output: str) -> str:
        counts: dict[str, int] = {}
        for node in self._nodes.values():
            counts[node.status] = counts.get(node.status, 0) + 1
        summary = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
        lines = [
            f"İş akışı '{self._spec.name}' (koşu {self.run_id}): {self._status}; "
            f"{self._runs.started_total} ajan başladı ({summary}).",
        ]
        if self._message:
            lines.append(self._message)
        lines.extend(
            f"- {node.status} · {node.id}: {node.label}"
            + (f" → {node.summary}" if node.summary and node.status != "tamam" else "")
            for node in self._nodes.values()
        )
        if output.strip():
            lines.extend(("", "## Son çıktı", cap_report(output)))
        return "\n".join(lines)


def _one_line(text: str, limit: int = 160) -> str:
    first = " ".join(text.split())
    return first if len(first) <= limit else first[: limit - 1] + "…"


async def run_workflow(
    deps: AgentDeps,
    spec: WorkflowSpec,
    plan: PlanGroup,
    inputs: Mapping[str, str | tuple[str, ...]],
    *,
    depth: int,
    run_agent: RunAgent,
    store: WorkflowStore,
) -> WorkflowResult:
    """Planı doğrula ve koştur; plan tavanı aşarsa `WorkflowError`."""
    limits = workflow_limits(deps, spec)
    check_plan(plan, limits)
    run = WorkflowRun(
        deps, spec, plan, inputs, depth=depth, run_agent=run_agent, store=store, limits=limits
    )
    return await run.execute()

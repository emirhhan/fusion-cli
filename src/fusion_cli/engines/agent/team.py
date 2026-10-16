"""Kişilikli alt ajanlar: canonical kapsam, ortak bütçe ve sahipli iptal.

Görevler çakışmayan yazma alanlarında paralel çalışır. Kimlikli olaylar her
üyenin kartına akar; bir child hatası bağımsız kardeş işi bozmaz. Ana tur
iptali ise tüm owned işleri bekleyerek kapatır.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.clock import SystemClock
from ...core.events import Channel, Event, EventPublisher, SubAgentFinished, SubAgentStarted
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...tools.capabilities import CapabilityRegistry, load_agent_prompt, map_tools
from .team_policy import allowed_tools as _allowed_tools
from .team_policy import child_execution as _child_execution
from .team_policy import member_brief as _member_brief
from .team_policy import summary as _summary
from .team_policy import team_report as _team_report
from .team_scope import changed_paths
from .team_scope import derive_sub_context as derive_sub_context
from .team_scope import schedule_waves as schedule_waves

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome

#: Alt ajan derinliği: alt ajan başka alt ajan başlatamaz. Ölçülmüş bir sınırdır
#: (bkz. `engine_tools.MAX_AGENT_DEPTH` tarihçesi); iç içe ajanlar bağlamı ve hız
#: kotasını katlayarak tüketir.
MAX_AGENT_DEPTH = 1
#: Kartta gösterilecek sonuç satırının en fazla karakteri.
SUMMARY_CHARS = 160

RunAgent = Callable[..., Awaitable["AgentOutcome"]]

_STRING = {"type": "string"}


@dataclass(frozen=True, slots=True)
class Persona:
    """Bir ekip üyesinin arayüzde ve modelde görünen kimliği."""

    name: str
    title: str
    avatar: str
    color: str
    prompt: str = ""
    #: Üyenin bildirdiği araç seti (Fusion adlarıyla); `None` = tam set.
    tools: frozenset[str] | None = None


#: Adı verilmeyen ya da kütüphanede bulunmayan görevler için genel yardımcı.
GENERIC_PERSONA = Persona(name="yardimci", title="Yardımcı", avatar="yardimci", color="gri")


@dataclass(frozen=True, slots=True)
class SubTask:
    """Bir alt ajana verilecek iş."""

    task: str
    persona: str = ""
    read_only: bool = False
    #: Yazılabilecek yollar (köke göreli). Boş + `read_only=False` = alan belirsiz.
    write_scope: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SubRun:
    """Bir alt ajan koşusunun sonucu."""

    sub_id: str
    persona: Persona
    text: str
    ok: bool
    tool_calls: int
    status: str = ""
    changed_paths: tuple[str, ...] = ()


class ScopedPublisher:
    """Olaylara ajan kimliğini basan yayıncı.

    Kimliği zaten dolu olay (daha içteki bir ajanın olayı) değiştirilmez.
    """

    def __init__(self, inner: EventPublisher, agent_id: str) -> None:
        self._inner = inner
        self._agent_id = agent_id

    def publish(self, event: Event) -> None:
        if event.agent_id:
            self._inner.publish(event)
            return
        self._inner.publish(dataclasses.replace(event, agent_id=self._agent_id))


def new_agent_id(persona: str) -> str:
    """Okunur ve çakışmaz alt ajan kimliği (`tasarimci-3f9a1c`)."""
    return f"{persona}-{uuid.uuid4().hex[:6]}"


def resolve_persona(library: CapabilityRegistry | None, name: str) -> Persona:
    """Adı ekip üyesine çevir; bulunamazsa genel yardımcı döner."""
    if library is None or not name.strip():
        return GENERIC_PERSONA
    agent = library.get_agent(name.strip())
    if agent is None:
        return GENERIC_PERSONA
    allowed = map_tools(agent.tools)
    return Persona(
        name=agent.name,
        title=agent.title or agent.name,
        avatar=agent.avatar or agent.name,
        color=agent.color,
        prompt=load_agent_prompt(agent.path),
        tools=frozenset(allowed) if allowed is not None else None,
    )


async def run_subagent(
    deps: AgentDeps,
    subtask: SubTask,
    *,
    depth: int,
    run_agent: RunAgent,
    group_size: int = 1,
) -> SubRun:
    """Tek bir alt ajanı kişiliğiyle başlat, olaylarını kimliğiyle akıt."""
    persona_error = ""
    try:
        persona = resolve_persona(deps.capabilities, subtask.persona)
    except Exception as error:
        persona = GENERIC_PERSONA
        persona_error = type(error).__name__
    sub_id = new_agent_id(persona.name)
    deps.publisher.publish(
        SubAgentStarted(
            task=subtask.task,
            sub_id=sub_id,
            persona=persona.name,
            title=persona.title,
            avatar=persona.avatar,
            color=persona.color,
            group_size=group_size,
            started_at=(deps.budget.clock if deps.budget is not None else SystemClock()).now(),
        )
    )
    started = time.monotonic()
    text = "Alt ajan tamamlanamadı."
    ok, tool_calls = False, 0
    status = "failed"
    context: ToolContext | None = None
    paths: tuple[str, ...] = ()
    try:
        if persona_error:
            text = f"Üye yüklenemedi ({persona_error})."
            return SubRun(sub_id, persona, text, False, 0)
        context = derive_sub_context(deps.tool_context, subtask)
        owned = deps.child_runs.start(
            sub_id, lambda: _run_child(deps, subtask, persona, sub_id, depth, run_agent, context)
        )
        try:
            outcome = await owned
        finally:
            deps.child_runs.detach(sub_id, owned)
        text = outcome.final_text or "Alt ajan boş yanıt verdi."
        ok = outcome.ok and bool(outcome.final_text.strip())
        tool_calls = outcome.tool_calls_made
        status = (
            "completed"
            if ok
            else "budget"
            if getattr(outcome, "budget_stopped", False)
            else "failed"
        )
    except asyncio.CancelledError:
        text = "Alt ajan iptal edildi."
        status = "cancelled"
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise
    except Exception as error:
        # Ham hata metni credential veya dış araç içeriği taşıyabilir.
        text = f"Alt ajan tamamlanamadı ({type(error).__name__})."
    finally:
        paths = changed_paths(context)
        deps.publisher.publish(
            SubAgentFinished(
                tool_calls=tool_calls,
                sub_id=sub_id,
                ok=ok,
                summary=_summary(text, SUMMARY_CHARS),
                elapsed_s=round(time.monotonic() - started, 1),
                status=status,
                changed_paths=paths,
            )
        )
    return SubRun(
        sub_id=sub_id,
        persona=persona,
        text=text,
        ok=ok,
        tool_calls=tool_calls,
        status=status,
        changed_paths=paths,
    )


async def _run_child(
    deps: AgentDeps,
    subtask: SubTask,
    persona: Persona,
    sub_id: str,
    depth: int,
    run_agent: RunAgent,
    context: ToolContext,
) -> AgentOutcome:
    from .loop import AgentDeps as _Deps

    sub_deps = _Deps(
        config=deps.config,
        publisher=ScopedPublisher(deps.publisher, sub_id),
        policy=deps.policy,
        tool_context=context,
        base_registry=deps.base_registry,
        asker=deps.asker,
        code_index=deps.code_index,
        lessons=deps.lessons,
        capabilities=deps.capabilities,
        health=deps.health,
        channel=Channel.SUBAGENT,
        budget=deps.budget,
        deadline=deps.deadline,
        child_runs=deps.child_runs,
        execution=_child_execution(deps, subtask),
        policy_factory=deps.policy_factory,
        approval_revision=deps.approval_revision,
        effect_recorder=deps.effect_recorder,
        ancestor_mutation_barrier=deps.mutation_blocked_by_pending_input,
    )
    try:
        return await run_agent(
            subtask.task,
            sub_deps,
            depth=depth + 1,
            self_review=False,
            extra_system=_member_brief(persona, subtask),
            allowed_tools=_allowed_tools(deps, persona, subtask),
        )
    finally:
        try:
            await sub_deps.questions.close()
        finally:
            deps.tool_context.touched.update(sub_deps.tool_context.touched)


async def run_team(
    deps: AgentDeps,
    subtasks: Sequence[SubTask],
    *,
    depth: int,
    run_agent: RunAgent,
) -> list[SubRun]:
    """Görevleri dalga dalga, dalga içinde eşzamanlı koştur; sonuçlar giriş sırasında."""
    # Her alan herhangi bir ajan başlamadan parent yetkisiyle doğrulanır.
    subtasks = [
        dataclasses.replace(
            task,
            write_scope=tuple(
                str(path) for path in derive_sub_context(deps.tool_context, task).write_scope or ()
            ),
        )
        for task in subtasks
    ]
    limit = max(1, deps.config.runtime.max_parallel_agents)
    gate = asyncio.Semaphore(limit)
    results: dict[int, SubRun] = {}

    async def _one(index: int, group_size: int) -> None:
        async with gate:
            results[index] = await run_subagent(
                deps, subtasks[index], depth=depth, run_agent=run_agent, group_size=group_size
            )

    for wave in schedule_waves(subtasks):
        async with asyncio.TaskGroup() as group:
            for index in wave:
                group.create_task(_one(index, len(wave)))
    return [results[index] for index in range(len(subtasks))]


# --------------------------------------------------------------------------- #
# Araçlar
# --------------------------------------------------------------------------- #

_SUBTASK_PROPERTIES: dict[str, object] = {
    "task": {**_STRING, "description": "alt ajana verilecek net, bağımsız görev"},
    "uzman": {
        **_STRING,
        "description": "ekip üyesinin adı (ör. mimar, kodcu, tasarimci, testci, "
        "arastirmaci, tarayici, gorselci, yonetmen); find_agent ile başkaları aranabilir",
    },
    "salt_okunur": {"type": "boolean", "description": "görev dosya değiştirmeyecekse true"},
    "yazma_alani": {
        "type": "array",
        "items": _STRING,
        "description": "görevin yazacağı dosya/dizinler (köke göreli); paralel koşu için gerekli",
    },
}


def spawn_agent_tool(deps: AgentDeps, *, depth: int, run_agent: RunAgent) -> Tool:
    """Tek bir alt görevi bir ekip üyesine devreden araç."""

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        subtask = _parse_subtask(args)
        if isinstance(subtask, str):
            return ToolResult.failure(subtask)
        if depth >= MAX_AGENT_DEPTH:
            return ToolResult.failure("Alt-ajan derinlik sınırına ulaşıldı; bu görevi kendin yap.")
        run = await run_subagent(deps, subtask, depth=depth, run_agent=run_agent)
        return ToolResult(run.text)

    return Tool(
        name="spawn_agent",
        description="Odaklı bir ALT-GÖREVİ temiz bağlamlı bir ekip üyesine devret; üye işi "
        "kendi araçlarıyla yapıp özet döner. Birden çok bağımsız iş varsa spawn_agents ile "
        "AYNI ANDA başlat. Basit işlerde kullanma.",
        parameters={
            "type": "object",
            "properties": _SUBTASK_PROPERTIES,
            "required": ["task"],
        },
        run=_run,
    )


def spawn_agents_tool(deps: AgentDeps, *, depth: int, run_agent: RunAgent) -> Tool:
    """Birden çok bağımsız alt görevi aynı anda koşturan araç."""

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        raw = args.get("gorevler")
        if not isinstance(raw, list) or not raw:
            return ToolResult.failure("'gorevler' boş olmayan bir liste olmalı.")
        if depth >= MAX_AGENT_DEPTH:
            return ToolResult.failure("Alt-ajan derinlik sınırına ulaşıldı; görevleri kendin yap.")
        subtasks: list[SubTask] = []
        for index, item in enumerate(raw):
            parsed = _parse_subtask(item if isinstance(item, dict) else {})
            if isinstance(parsed, str):
                return ToolResult.failure(f"gorevler[{index}]: {parsed}")
            subtasks.append(parsed)
        runs = await run_team(deps, subtasks, depth=depth, run_agent=run_agent)
        return ToolResult(_team_report(runs))

    return Tool(
        name="spawn_agents",
        description="Birbirinden BAĞIMSIZ birden çok alt görevi ekip üyelerine dağıt ve AYNI "
        "ANDA koştur (ör. biri araştırırken öteki tasarlasın). Dosya yazan her görev için "
        "yazma_alani ver; alanlar ayrıksa paralel, belirsizse sırayla koşar. Sonuçlar "
        "görev sırasıyla döner.",
        parameters={
            "type": "object",
            "properties": {
                "gorevler": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": _SUBTASK_PROPERTIES,
                        "required": ["task"],
                    },
                }
            },
            "required": ["gorevler"],
        },
        run=_run,
    )


def _parse_subtask(args: ToolArgs) -> SubTask | str:
    task = args.get("task")
    if not isinstance(task, str) or not task.strip():
        return "'task' alanı boş olmayan bir metin olmalı."
    persona = args.get("uzman", "")
    scope = args.get("yazma_alani", ())
    if not isinstance(scope, (list, tuple)) or not all(isinstance(item, str) for item in scope):
        return "'yazma_alani' metin listesi olmalı."
    return SubTask(
        task=task.strip(),
        persona=persona if isinstance(persona, str) else "",
        read_only=args.get("salt_okunur") is True,
        write_scope=tuple(item.strip() for item in scope if item.strip()),
    )

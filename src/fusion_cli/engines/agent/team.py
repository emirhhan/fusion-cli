"""Alt ajan ekibi — kişilikli, kimlikli ve gerektiğinde PARALEL alt ajanlar.

Eskiden alt ajan kimliksizdi: olay yalnız görev metnini taşıyordu, arayüz bütün
adımları tek "alt ajan" etiketiyle aynı listeye döküyordu ve iki alt ajan ancak
sırayla koşabiliyordu. Bu modül üç şeyi ekler:

- **Kişilik.** Her alt ajan bir ekip üyesidir (ünvan, avatar, renk, talimat, araç
  seti). Yerleşik ekip `config/roster/`'dadır; kullanıcı `.claude/agents` altına
  aynı adla kendi üyesini yazarsa o kazanır.
- **Kimlik.** Alt ajanın her olayı `agent_id` taşır (`ScopedPublisher`); arayüz
  her ajanın kartını ayrı çizer.
- **Paralellik.** `spawn_agents` birden çok görevi aynı anda koşturur. Aynı dosyayı
  iki ajanın ezmemesi için zamanlayıcı görevleri DALGALARA böler: salt okuyanlar ve
  yazma alanları ayrık olanlar birlikte, alanı belirsiz yazanlar tek başına koşar.
  Eşzamanlılık `runtime.max_parallel_agents` ile sınırlıdır; asıl hız sınırını
  ortak hız defteri korur (bkz. `providers/rate_gate.py`).
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.events import Channel, Event, EventPublisher, SubAgentFinished, SubAgentStarted
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...tools.capabilities import CapabilityRegistry, load_agent_prompt, map_tools

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


def schedule_waves(subtasks: Sequence[SubTask]) -> list[list[int]]:
    """Görevleri birlikte koşabilecek dalgalara böl (sıra korunur).

    Kural: salt okuyan görev her dalgaya katılır; yazma alanı bildiren görev,
    dalgadaki alanlarla çakışmıyorsa katılır; alanı belirsiz yazan görev tek
    başına bir dalgadır (neye dokunacağı bilinmediği için kimseyle koşmaz).
    """
    waves: list[list[int]] = []
    current: list[int] = []
    claimed: list[Path] = []
    for index, subtask in enumerate(subtasks):
        if subtask.read_only:
            current.append(index)
            continue
        scope = [Path(raw) for raw in subtask.write_scope]
        if scope and not any(_overlaps(path, taken) for path in scope for taken in claimed):
            current.append(index)
            claimed.extend(scope)
            continue
        if current:
            waves.append(current)
        if scope:
            current, claimed = [index], list(scope)
        else:
            waves.append([index])
            current, claimed = [], []
    if current:
        waves.append(current)
    return waves


def _overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


async def run_subagent(
    deps: AgentDeps,
    subtask: SubTask,
    *,
    depth: int,
    run_agent: RunAgent,
    group_size: int = 1,
) -> SubRun:
    """Tek bir alt ajanı kişiliğiyle başlat, olaylarını kimliğiyle akıt."""
    from .loop import AgentDeps as _Deps

    persona = resolve_persona(deps.capabilities, subtask.persona)
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
        )
    )
    started = time.monotonic()
    sub_deps = _Deps(
        config=deps.config,
        publisher=ScopedPublisher(deps.publisher, sub_id),
        policy=deps.policy,
        tool_context=derive_sub_context(deps.tool_context, subtask),
        base_registry=deps.base_registry,
        asker=deps.asker,
        code_index=deps.code_index,
        lessons=deps.lessons,
        capabilities=deps.capabilities,
        health=deps.health,
        channel=Channel.SUBAGENT,
    )
    outcome = await run_agent(
        subtask.task,
        sub_deps,
        depth=depth + 1,
        self_review=False,
        extra_system=_member_brief(persona, subtask),
        allowed_tools=_allowed_tools(deps, persona, subtask),
    )
    text = outcome.final_text or "(alt ajan boş yanıt verdi)"
    deps.publisher.publish(
        SubAgentFinished(
            tool_calls=outcome.tool_calls_made,
            sub_id=sub_id,
            ok=outcome.ok,
            summary=_summary(text),
            elapsed_s=round(time.monotonic() - started, 1),
        )
    )
    return SubRun(
        sub_id=sub_id,
        persona=persona,
        text=text,
        ok=outcome.ok,
        tool_calls=outcome.tool_calls_made,
    )


async def run_team(
    deps: AgentDeps,
    subtasks: Sequence[SubTask],
    *,
    depth: int,
    run_agent: RunAgent,
) -> list[SubRun]:
    """Görevleri dalga dalga, dalga içinde eşzamanlı koştur; sonuçlar giriş sırasında."""
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


def derive_sub_context(context: ToolContext, subtask: SubTask | None = None) -> ToolContext:
    """Alt ajan bağlamı: görev listesi AYRI, değişiklik kümesi ORTAK.

    Alt ajan temiz bir görev listesiyle çalışır — ana ajanın listesini ezmesi
    kullanıcının takip ettiği planı bozardı. `touched` PAYLAŞILIR: alt ajanın
    yazdığı dosya ana doğrulama kapısından sızmasın. Erişim sınırı aynen taşınır;
    yazma alanı bildirildiyse alt ajan yalnız oraya yazar.
    """
    scope: tuple[Path, ...] | None = context.write_scope
    if subtask is not None and subtask.write_scope:
        scope = tuple(context.root / raw for raw in subtask.write_scope)
    return ToolContext(
        root=context.root,
        touched=context.touched,
        changes=context.changes,
        restrict_to_root=context.restrict_to_root,
        extra_roots=context.extra_roots,
        chrome=context.chrome,
        write_scope=scope,
    )


def _allowed_tools(deps: AgentDeps, persona: Persona, subtask: SubTask) -> set[str] | None:
    allowed: set[str] | None = set(persona.tools) if persona.tools is not None else None
    if not subtask.read_only:
        return allowed
    readers = {tool.name for tool in deps.base_registry if not tool.mutating}
    return readers if allowed is None else allowed & readers


def _member_brief(persona: Persona, subtask: SubTask) -> str:
    """Üyenin talimatı + bu görevin sınırları (modelin göreceği kısa not)."""
    parts = [persona.prompt.strip()] if persona.prompt.strip() else []
    if subtask.read_only:
        parts.append("Bu görevde SALT OKUYORSUN: dosya değiştirme, yalnız bulgularını raporla.")
    elif subtask.write_scope:
        alan = ", ".join(subtask.write_scope)
        parts.append(
            f"Yalnız şu yollara yazabilirsin: {alan}. Başka ajanlar aynı anda başka "
            "dosyalarda çalışıyor; alanın dışına çıkma."
        )
    return "\n\n".join(parts)


def _summary(text: str) -> str:
    first = " ".join(text.strip().split())
    return first if len(first) <= SUMMARY_CHARS else first[: SUMMARY_CHARS - 1] + "…"


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


def _team_report(runs: Sequence[SubRun]) -> str:
    """Ana ajana dönen birleşik rapor: her üyenin sonucu kendi başlığıyla."""
    return "\n\n".join(
        f"## {run.persona.title} ({run.sub_id}) — {'tamam' if run.ok else 'yarım'}\n{run.text}"
        for run in runs
    )

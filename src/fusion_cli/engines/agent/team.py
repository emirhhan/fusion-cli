"""Kişilikli alt ajanlar: canonical kapsam, ortak bütçe ve sahipli iptal.

Görevler çakışmayan yazma alanlarında paralel çalışır. Kimlikli olaylar her
üyenin kartına akar; bir child hatası bağımsız kardeş işi bozmaz. Ana tur
iptali ise tüm owned işleri bekleyerek kapatır.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.clock import SystemClock
from ...core.errors import PathAccessError, WorktreeError
from ...core.events import Channel, Event, EventPublisher, SubAgentFinished, SubAgentStarted
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...core.worktree import LeaveOutcome, Worktree, enter_worktree, leave_worktree
from ...memory.plain_memory import AGENT_MEMORY_SCOPES
from ...tools.capabilities import (
    CapabilityRegistry,
    expand_tool_patterns,
    load_agent_prompt,
    map_tools,
    unmapped_tools,
)
from . import team_fork, team_settings
from .team_policy import allowed_tools as _allowed_tools
from .team_policy import cap_report as _cap_report
from .team_policy import child_execution as _child_execution
from .team_policy import member_brief as _member_brief
from .team_policy import summary as _summary
from .team_policy import team_report as _team_report
from .team_scope import changed_paths
from .team_scope import derive_sub_context as derive_sub_context
from .team_scope import schedule_waves as schedule_waves

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome

_LOG = logging.getLogger(__name__)

#: Alt ajan derinliğinin YEDEK tavanı: yapılandırma okunamazsa alt ajan başka alt ajan
#: başlatamaz. Asıl değer `runtime.max_agent_depth` (P-035; Claude Code 3 derinliğe izin
#: verir); iç içe ajanlar bağlamı ve hız kotasını katlayarak tüketir, bu yüzden her
#: derinlik adım bütçesini yarılar (`child_step_limit`).
MAX_AGENT_DEPTH = 1
#: Kartta gösterilecek sonuç satırının en fazla karakteri.
SUMMARY_CHARS = 160
#: Derinlik ne olursa olsun bir alt ajana bırakılan en az model çağrısı.
MIN_CHILD_STEPS = 8

DEPTH_LIMIT_MESSAGE = "Alt-ajan derinlik sınırına ulaşıldı; bu görevi kendin yap."
SUBAGENT_BUDGET_MESSAGE = (
    "Bu turda alt ajan bütçesi doldu ({limit} alt ajan başlatıldı); kalan işi kendin yap."
)


def max_agent_depth(deps: AgentDeps) -> int:
    """Yapılandırılmış derinlik tavanı; eski yapılandırmada yedek sabit."""
    return max(1, int(getattr(deps.config.runtime, "max_agent_depth", MAX_AGENT_DEPTH)))


def depth_limit_reached(deps: AgentDeps, depth: int) -> bool:
    """`depth` derinliğindeki ajan yeni bir alt ajan açamaz mı?"""
    return depth >= max_agent_depth(deps)


def subagent_budget_exhausted(deps: AgentDeps) -> str | None:
    """Kök turun toplam alt ajan bütçesi dolduysa modele dönecek mesaj, değilse None."""
    limit = int(getattr(deps.config.runtime, "max_subagents_per_turn", 0) or 0)
    started = getattr(deps.child_runs, "started_total", 0)
    if limit > 0 and started >= limit:
        return SUBAGENT_BUDGET_MESSAGE.format(limit=limit)
    return None


def child_step_limit(deps: AgentDeps, depth: int, requested: int | None = None) -> int | None:
    """Derinliğe göre azalan adım bütçesi: her kat öncekinin yarısı.

    `requested` (kişiliğin `max_turns` alanı) daha darsa o geçerlidir ama yapılandırılmış
    `agent_max_steps` tavanını AŞAMAZ (ölçüldü, 31 Ekim: depodan gelen `maxTurns: 500`
    derinlik 0'da tek başına geçerli oluyordu). Derinlik 0'ın çocuğu tam bütçeyi alır; daha
    içteki ajanlar bağlamı katlamasın diye yarılanır.
    """
    halved: int | None = None
    base = deps.config.runtime.agent_max_steps
    if depth >= 1 and base:
        halved = max(MIN_CHILD_STEPS, base >> depth)
    if requested and base:
        requested = min(requested, base)
    candidates = [limit for limit in (halved, requested) if limit is not None and limit > 0]
    return min(candidates) if candidates else None


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
    #: Tanımdaki ayarlar (P-034; bkz. `team_settings`). Boş/0 = üst ajandan miras.
    model: str = ""
    permission_mode: str = ""
    max_turns: int = 0
    skills: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()
    #: user | project | local: alt ajanın kalıcı belleği (P-055); boş = yok.
    memory_scope: str = ""
    effort: str = ""
    #: `disallowedTools` Fusion adlarıyla; `tools`'tan sonra çıkarılır.
    disallowed_tools: frozenset[str] = frozenset()
    #: Tanımda geçen ama Fusion'da karşılığı olmayan araç adları (uyarı için).
    unknown_tools: tuple[str, ...] = ()


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
    #: Ana konuşmanın bağlamını devral (fork, P-054): alt ajan temiz değil, ana geçmişin
    #: kırpılmış görünümüyle başlar. `/subtask`, `baglam_miras: true` ve `context: fork`.
    inherit_context: bool = False
    #: Üst turun bu göreve kattığı ek sistem notu (oturum kişiliği, seçilen beceri metni,
    #: kip istemi): üyenin kendi talimatından SONRA brife girer. Ölçüldü (31 Ekim): fork
    #: turu bunları atıyordu, `context: fork` becerisi boş çalışıyordu.
    brief: str = ""
    #: Üst turun araç TAVANI (`None` = sınırsız): üyenin kümesiyle kesişir, genişletmez.
    #: Salt-okur oturum kişiliği fork içinde yazamasın diye.
    tool_cap: frozenset[str] | None = None
    #: Üst turun yasak araçları (oturum kişiliğinin `disallowedTools`u); desen açılır.
    tool_deny: frozenset[str] = frozenset()
    #: Görev mesajına eklenen görseller (data URI); fork turunda kullanıcının ekleri.
    images: tuple[str, ...] = ()
    #: Üst turun adım tavanı; kişiliğin `maxTurns`'ü ve derinlik bütçesiyle en küçüğü geçer.
    step_limit: int | None = None
    #: "worktree" ise üye kendi git çalışma ağacında yazar; ana proje değişmez.
    isolation: str = ""


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
    disallowed = map_tools(agent.disallowed_tools) if agent.disallowed_tools else None
    unknown = unmapped_tools(agent.tools) + unmapped_tools(agent.disallowed_tools)
    if unknown:
        _LOG.warning(
            "ajan tanımında tanınmayan araç adı", extra={"ajan": agent.name, "araclar": unknown}
        )
    return Persona(
        name=agent.name,
        title=agent.title or agent.name,
        avatar=agent.avatar or agent.name,
        color=agent.color,
        prompt=load_agent_prompt(agent.path),
        tools=frozenset(allowed) if allowed is not None else None,
        model=agent.model,
        permission_mode=agent.permission_mode,
        max_turns=agent.max_turns,
        skills=agent.skills,
        mcp_servers=agent.mcp_servers,
        memory_scope=agent.memory if agent.memory in AGENT_MEMORY_SCOPES else "",
        effort=agent.effort,
        disallowed_tools=frozenset(disallowed or ()),
        unknown_tools=unknown,
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
            depth=depth + 1,
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
        budget_message = subagent_budget_exhausted(deps)
        if budget_message is not None:
            text = budget_message
            status = "budget"
            return SubRun(sub_id, persona, text, False, 0, status=status)
        worktree = await _isolated_worktree(deps.tool_context, subtask, sub_id)
        context = derive_sub_context(
            deps.tool_context, subtask, root=worktree.path if worktree is not None else None
        )
        owned = deps.child_runs.start(
            sub_id, lambda: _run_child(deps, subtask, persona, sub_id, depth, run_agent, context)
        )
        try:
            outcome = await owned
        finally:
            deps.child_runs.detach(sub_id, owned)
        text = outcome.final_text or "Alt ajan boş yanıt verdi."
        if worktree is not None:
            text += await asyncio.to_thread(_settle_worktree, worktree)
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
    except (PathAccessError, WorktreeError) as error:
        # Yazma alanı kök dışı/izinsiz ya da çalışma ağacı kurulamadı: mesaj Fusion'ın
        # kendi denetiminden gelir (sır taşımaz) ve modelin düzeltebileceği bilgidir (A4-39).
        text = f"Alt ajan başlatılamadı: {error}"
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
    from .engine_tools import build_agent_registry
    from .loop import AgentDeps as _Deps

    label = team_settings.agent_label(persona, sub_id)
    policy, policy_factory = team_settings.child_policies(deps, persona, label)
    sub_deps = _Deps(
        config=team_settings.child_config(deps.config, persona),
        publisher=ScopedPublisher(deps.publisher, sub_id),
        policy=policy,
        tool_context=context,
        base_registry=deps.base_registry,
        asker=deps.asker,
        code_index=deps.code_index,
        lessons=deps.lessons,
        capabilities=deps.capabilities,
        health=deps.health,
        channel=Channel.SUBAGENT,
        # Aynı sistem istemli paralel alt ajanlar web taşımasında ayrı sohbet tutsun (P1-31).
        conversation_id="/".join(part for part in (deps.conversation_id, sub_id) if part),
        budget=deps.budget,
        deadline=deps.deadline,
        child_runs=deps.child_runs,
        execution=_child_execution(deps, subtask),
        policy_factory=policy_factory,
        approval_revision=deps.approval_revision,
        # Torun bu ajanın SIKILAŞTIRILMIŞ kipini temel alır, oturumun kipini değil.
        approval_mode=team_settings.child_approval_mode(deps, persona),
        policy_for_mode=getattr(deps, "policy_for_mode", None),
        # Tanımdaki `memory` alanı: ajana özel BELLEK.md (P-055); blok ve araçlar bundan gelir.
        plain_memory=team_settings.child_memory(deps, persona),
        # Belleği olan ajan derslerini de kendine ayırır; olmayan ortak havuza yazar (P-055).
        lesson_owner=persona.name if persona.memory_scope else "",
        effect_recorder=deps.effect_recorder,
        ancestor_mutation_barrier=deps.mutation_blocked_by_pending_input,
    )
    # Tanımdaki `model` yalnız bu alt ajanın çağrılarını değiştirir (P-034).
    sub_deps.active_model_override = team_settings.child_model(persona, deps.config.agent)
    available = build_agent_registry(sub_deps, depth=depth + 1, run_agent=run_agent).names()
    # Fork (P-054): ana geçmişin sistemsiz, kırpılmış görünümü alt ajanın başlangıcı olur.
    inherited = (
        team_fork.fork_history(team_fork.parent_history(deps)) if subtask.inherit_context else None
    )
    try:
        return await run_agent(
            subtask.task,
            sub_deps,
            history=inherited,
            depth=depth + 1,
            self_review=False,
            extra_system=_member_brief(
                persona,
                subtask,
                skills=team_settings.preloaded_skills(deps, persona),
                fork_note=team_fork.FORK_BRIEF if inherited is not None else "",
            ),
            allowed_tools=_capped_tools(
                _allowed_tools(deps, persona, subtask, available=available),
                subtask.tool_cap,
                available,
                deny=subtask.tool_deny,
            ),
            step_limit=child_step_limit(
                deps, depth, requested=_min_limit(persona.max_turns or None, subtask.step_limit)
            ),
            images=subtask.images,
        )
    finally:
        try:
            await sub_deps.questions.close()
        finally:
            deps.tool_context.touched.update(sub_deps.tool_context.touched)
            # Alt ajanın `play_probe` ile sınadığı oyun parent kapanışında yeniden oynanmasın
            # (A4-41): kanıt da parent'a döner.
            deps.tool_context.probed_games.update(sub_deps.tool_context.probed_games)


def _capped_tools(
    allowed: set[str] | None,
    cap: frozenset[str] | None,
    available: tuple[str, ...],
    *,
    deny: frozenset[str] = frozenset(),
) -> set[str] | None:
    """Üst turun araç tavanıyla kesişim ve yasak kümesinin farkı: yalnız daralır."""
    if cap is not None:
        expanded = expand_tool_patterns(set(cap), available)
        allowed = expanded if allowed is None else allowed & expanded
    if deny:
        base = set(available) if allowed is None else allowed
        allowed = base - expand_tool_patterns(set(deny), available)
    return allowed


def _min_limit(*limits: int | None) -> int | None:
    values = [limit for limit in limits if limit is not None and limit > 0]
    return min(values) if values else None


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


async def _isolated_worktree(
    context: ToolContext, subtask: SubTask, sub_id: str
) -> Worktree | None:
    """`izolasyon: "worktree"` ise üyeye `.fusion/worktrees/ajan-<kimlik>` ağacı aç.

    Ağaç oturumun KENDİ kökünün HEAD'inden dallanır (oturum bir ağaçtaysa o dalından).
    Üye bitince `_settle_worktree` karar verir: iş kaldıysa ağaç kalır, kalmadıysa
    kaldırılır. Salt okuyan üye için ağaç açılmaz.
    """
    if subtask.isolation != "worktree" or subtask.read_only:
        return None
    name = "ajan-" + re.sub(r"[^A-Za-z0-9._-]", "-", sub_id)[:48]
    return await asyncio.to_thread(enter_worktree, context.root, name)


def _settle_worktree(worktree: Worktree) -> str:
    """Üye bittikten sonra ağacın akıbeti: iş varsa korunur ve yolu söylenir, yoksa kaldırılır.

    Ölçüldü (31 Ekim): her çağrıda ajan-<kimlik> ağacı ve dalı kalıyor, üye dosya
    değiştirmese de birikiyordu. Kaldırma `leave_worktree`'nin kendi temizlik kanıtına dayanır.
    """
    try:
        result = leave_worktree(worktree)
    except WorktreeError as error:
        return f"\n\n[Çalışma ağacı] {worktree.path} korunuyor; temizlik ölçülemedi: {error}"
    if result.outcome is LeaveOutcome.REMOVED:
        return ""
    return (
        f"\n\n[Çalışma ağacı] Değişiklikler ana projede DEĞİL, {worktree.path} içinde "
        f"(dal {worktree.branch}). Birleştirmek için: git merge {worktree.branch}"
    )


_SUBTASK_PROPERTIES: dict[str, object] = {
    "task": {**_STRING, "description": "alt ajana verilecek net, bağımsız görev"},
    "uzman": {
        **_STRING,
        "description": "ekip üyesinin adı: keşif/arama için explore (salt-okur), plan "
        "çıkarmak için plan, ayrıca mimar, kodcu, tasarimci, testci, arastirmaci, tarayici, "
        "gorselci, yonetmen; find_agent ile başkaları aranabilir",
    },
    "salt_okunur": {"type": "boolean", "description": "görev dosya değiştirmeyecekse true"},
    "baglam_miras": {
        "type": "boolean",
        "description": "true ise alt ajan bu konuşmanın bağlamını devralır (fork): uzun "
        "ara görevi ana bağlamı şişirmeden yürütmek için; varsayılan temiz bağlam",
    },
    "yazma_alani": {
        "type": "array",
        "items": _STRING,
        "description": "görevin yazacağı dosya/dizinler (köke göreli); paralel koşu için gerekli",
    },
    "izolasyon": {
        **_STRING,
        "description": "'worktree' ise üye izole bir git çalışma ağacında yazar; ana proje "
        "değişmez, iş kaldıysa sonuç dal olarak kalır. Ağaç bu kökün son commit'inden "
        "açılır: commit edilmemiş değişiklikler üyeye GÖRÜNMEZ",
    },
}


def spawn_agent_tool(deps: AgentDeps, *, depth: int, run_agent: RunAgent) -> Tool:
    """Tek bir alt görevi bir ekip üyesine devreden araç."""

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        subtask = _parse_subtask(args)
        if isinstance(subtask, str):
            return ToolResult.failure(subtask)
        if depth_limit_reached(deps, depth):
            return ToolResult.failure(DEPTH_LIMIT_MESSAGE)
        run = await run_subagent(deps, subtask, depth=depth, run_agent=run_agent)
        return ToolResult(_cap_report(run.text))

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
        if depth_limit_reached(deps, depth):
            return ToolResult.failure(DEPTH_LIMIT_MESSAGE)
        subtasks: list[SubTask] = []
        for index, item in enumerate(raw):
            parsed = _parse_subtask(item if isinstance(item, dict) else {})
            if isinstance(parsed, str):
                return ToolResult.failure(f"gorevler[{index}]: {parsed}")
            subtasks.append(parsed)
        try:
            runs = await run_team(deps, subtasks, depth=depth, run_agent=run_agent)
        except PathAccessError as error:
            # Geçersiz `yazma_alani` ham istisna olarak değil modelin düzeltebileceği sonuç (A4-39).
            return ToolResult.failure(f"Yazma alanı geçersiz: {error}")
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


_FALSE_WORDS = frozenset({"false", "no", "hayır", "hayir", "0", "off", ""})


def _parse_read_only(value: object) -> bool:
    """`salt_okunur` değerini AÇIK-GÜVENLİ oku: belirsizse salt-okuma say.

    Ölçüldü (29 Ekim): `is True` katı karşılaştırması `"true"`, `1`, `"evet"` gibi zayıf
    model çıktılarını `False` sayıp görevi YAZMA YETKİLİ yapıyordu (A4-09). Alan hiç
    verilmediyse varsayılan (yazma yetkili) korunur; açıkça yanlış denmediyse kısıtlanır.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().casefold() not in _FALSE_WORDS
    return True


def _parse_subtask(args: ToolArgs) -> SubTask | str:
    task = args.get("task")
    if not isinstance(task, str) or not task.strip():
        return "'task' alanı boş olmayan bir metin olmalı."
    persona = args.get("uzman", "")
    scope = args.get("yazma_alani", ())
    if not isinstance(scope, (list, tuple)) or not all(isinstance(item, str) for item in scope):
        return "'yazma_alani' metin listesi olmalı."
    isolation = args.get("izolasyon", "")
    if isolation and isolation != "worktree":
        return "'izolasyon' yalnız 'worktree' olabilir."
    return SubTask(
        task=task.strip(),
        persona=persona if isinstance(persona, str) else "",
        read_only=_parse_read_only(args.get("salt_okunur")),
        write_scope=tuple(item.strip() for item in scope if item.strip()),
        inherit_context=_parse_true(args.get("baglam_miras")),
        isolation=str(isolation or ""),
    )


_TRUE_WORDS = frozenset({"true", "evet", "1", "yes", "on"})


def _parse_true(value: object) -> bool:
    """`baglam_miras` KAPALI-GÜVENLİ okunur: yalnız açık doğru değer fork açar."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return isinstance(value, str) and value.strip().casefold() in _TRUE_WORDS

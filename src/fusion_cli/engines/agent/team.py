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
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ...config.models import McpServerConfig
from ...config.worktree_settings import enter_configured_worktree
from ...core.clock import SystemClock
from ...core.errors import ConfigError, PathAccessError, WorktreeError
from ...core.events import Channel, Event, EventPublisher, SubAgentFinished, SubAgentStarted
from ...core.hooks.events import HookSet
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...core.worktree import LeaveOutcome, Worktree, leave_worktree
from ...memory.plain_memory import AGENT_MEMORY_SCOPES
from ...tools import job_lifetime
from ...tools.capabilities import (
    CapabilityRegistry,
    agent_prompt,
    expand_tool_patterns,
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
#: başlatamaz. Asıl değer `runtime.max_agent_depth` (Claude Code: ana konuşmanın altında 3
#: kat) ya da `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`.
MAX_AGENT_DEPTH = 1
#: Kartta gösterilecek sonuç satırının en fazla karakteri.
SUMMARY_CHARS = 160
DEPTH_LIMIT_MESSAGE = "Alt-ajan derinlik sınırına ulaşıldı; bu görevi kendin yap."
#: maxTurns sınırına ulaşan alt ajan sonucunun başı.
PARTIAL_PREFIX = "[Kısmi çıktı: alt ajan maxTurns sınırına ulaştı; SendMessage ile sürdürülebilir.]"
#: Claude Code'un eşzamanlı alt ajan sınırı iletisi (aynen).
CONCURRENT_LIMIT_MESSAGE = "Concurrent subagent limit reached ({limit} alt ajan çalışıyor)."
SUBAGENT_BUDGET_MESSAGE = (
    "Bu turda alt ajan bütçesi doldu ({limit} alt ajan başlatıldı); kalan işi kendin yap."
)


def max_agent_depth(deps: AgentDeps) -> int:
    """Claude ortam değişkeni → yapılandırılmış tavan; eski yapılandırmada yedek sabit."""
    launch = getattr(getattr(deps.config, "agent_launch", None), "max_spawn_depth", 0) or 0
    if launch > 0:
        return int(launch)
    return max(1, int(getattr(deps.config.runtime, "max_agent_depth", MAX_AGENT_DEPTH)))


def concurrent_limit(deps: AgentDeps) -> int:
    """Aynı anda çalışabilecek alt ajan sayısı (Claude Code varsayılanı 20)."""
    launch = getattr(getattr(deps.config, "agent_launch", None), "max_concurrent_subagents", 0)
    if launch:
        return int(launch)
    return max(1, int(getattr(deps.config.runtime, "max_parallel_agents", 20)))


def concurrent_limit_reached(deps: AgentDeps) -> str | None:
    """Oturumda sınır kadar alt ajan çalışıyorsa modele dönecek ileti."""
    limit = concurrent_limit(deps)
    active = getattr(deps.child_runs, "active_count", 0)
    return CONCURRENT_LIMIT_MESSAGE.format(limit=limit) if active >= limit else None


def depth_limit_reached(deps: AgentDeps, depth: int) -> bool:
    """`depth` derinliğindeki ajan yeni bir alt ajan açamaz mı?"""
    return depth >= max_agent_depth(deps)


def subagent_budget_exhausted(deps: AgentDeps) -> str | None:
    """Kök turun toplam alt ajan bütçesi dolduysa modele dönecek mesaj, değilse None."""
    limit = int(getattr(deps.config.runtime, "max_subagents_per_turn", 0) or 0)
    started = deps.child_runs.started_for_current_turn + getattr(
        deps.child_runs, "pending_starts", 0
    )
    if limit > 0 and started >= limit:
        return SUBAGENT_BUDGET_MESSAGE.format(limit=limit)
    return None


def child_step_limit(deps: AgentDeps, depth: int, requested: int | None = None) -> int | None:
    """Alt ajanın adım tavanı: tanımdaki `maxTurns` olduğu gibi uygulanır (#36).

    Claude Code derinliğe göre bütçe yarılamaz (#29). Kullanıcının `agent_max_steps`
    tavanı aşılmaz (ölçüldü, 31 Ekim: depodan gelen `maxTurns: 500` deliyordu); `depth`
    eski çağıranlar için imzada kalır.
    """
    del depth
    base = deps.config.runtime.agent_max_steps
    if requested and base:
        return min(requested, base)
    return requested or None


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
    #: Yerleşik keşif/plan ajanında ilk proje talimatları yüklenmez.
    omit_initial_instructions: bool = False
    initial_prompt: str = ""
    #: `autoCompactWindow` (belirteç): alt ajanın özetleme eşiğini düşürür; 0 = oturumunki.
    auto_compact_window: int = 0
    #: `experimental.cacheTtl` (`5m` | `1h`).
    cache_ttl: str = ""
    hook_definitions: HookSet = field(default_factory=HookSet, repr=False)
    inline_mcp_servers: tuple[McpServerConfig, ...] = field(default=(), repr=False)
    background: bool = False
    #: Tanımdaki `isolation`; `worktree` ise çağrı istemese de ajan ayrı ağaçta koşar (#22).
    isolation: str = ""
    source: str = ""
    definition_path: Path | None = None
    allowed_agent_types: tuple[str, ...] | None = None


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
    model: str = ""
    name: str = ""
    resume: str = ""
    agent_id: str = ""
    background: bool = False
    #: Çağrıdaki `effort`; tanımdaki `effort` alanını yalnız bu koşu için ezer.
    effort: str = ""


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
    prefix = re.sub(r"[^a-zA-Z0-9_-]", "-", persona)[:48].strip("-") or "ajan"
    return f"{prefix}-{uuid.uuid4().hex}"


def resolve_persona(library: CapabilityRegistry | None, name: str) -> Persona:
    """Adı ekip üyesine çevir; bulunamazsa genel yardımcı döner."""
    if library is None or not name.strip():
        return GENERIC_PERSONA
    agent = library.get_agent(name.strip())
    if agent is None:
        return GENERIC_PERSONA
    from .agent_runtime_context import agent_type_subset, child_tool_names

    allowed = map_tools(child_tool_names(agent.tools))
    disallowed = map_tools(agent.disallowed_tools) if agent.disallowed_tools else None
    unknown = unmapped_tools(child_tool_names(agent.tools)) + unmapped_tools(agent.disallowed_tools)
    if unknown:
        _LOG.warning(
            "ajan tanımında tanınmayan araç adı", extra={"ajan": agent.name, "araclar": unknown}
        )
    return Persona(
        name=agent.name,
        title=agent.title or agent.name,
        avatar=agent.avatar or agent.name,
        color=agent.color,
        prompt=agent_prompt(agent),
        tools=frozenset(allowed) if allowed is not None else None,
        model=agent.model,
        permission_mode=team_settings.agent_permission_mode(agent),
        max_turns=agent.max_turns,
        skills=agent.skills,
        mcp_servers=agent.mcp_servers,
        memory_scope=agent.memory if agent.memory in AGENT_MEMORY_SCOPES else "",
        effort=agent.effort,
        disallowed_tools=frozenset(disallowed or ()),
        unknown_tools=unknown,
        omit_initial_instructions=(
            agent.omit_claude_md or (agent.source == "fusion" and agent.name in {"explore", "plan"})
        ),
        initial_prompt=agent.initial_prompt,
        auto_compact_window=agent.auto_compact_window,
        cache_ttl=agent.cache_ttl,
        hook_definitions=agent.hook_definitions,
        inline_mcp_servers=agent.inline_mcp_servers,
        background=agent.background,
        isolation=agent.isolation,
        source=agent.source,
        definition_path=agent.path,
        allowed_agent_types=agent_type_subset(agent.tools),
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
    cap = deps.runtime_tool_cap
    if cap is not None:
        subtask = dataclasses.replace(
            subtask, tool_cap=cap if subtask.tool_cap is None else cap & subtask.tool_cap
        )
    subtask = dataclasses.replace(subtask, tool_deny=subtask.tool_deny | deps.denied_tools)
    persona_error = ""
    try:
        persona = resolve_persona(deps.capabilities, subtask.persona)
    except Exception as error:
        persona = GENERIC_PERSONA
        persona_error = type(error).__name__
    if subtask.effort:
        persona = dataclasses.replace(persona, effort=subtask.effort)
    if persona.memory_scope and not getattr(deps.config.runtime, "auto_memory", True):
        # Claude Code: ajan belleği otomatik belleğin parçasıdır; kapalıyken alan etkisizdir.
        persona = dataclasses.replace(persona, memory_scope="")
    from .agent_runtime_context import launch_denial

    denial = launch_denial(deps, persona, subtask.persona)
    if denial:
        return SubRun("", persona, denial, False, 0, status="denied")
    sub_id = subtask.agent_id or new_agent_id(persona.name)
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
        if subtask.agent_id and deps.child_runs.running(subtask.agent_id):
            limit = deps.config.runtime.max_subagents_per_turn
            if not limit or deps.child_runs.started_for_current_turn < limit:
                budget_message = None
        if budget_message is not None:
            text = budget_message
            status = "budget"
            return SubRun(sub_id, persona, text, False, 0, status=status)
        if persona.isolation == "worktree" and not subtask.isolation:
            subtask = dataclasses.replace(subtask, isolation="worktree")
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
            # Claude: ön plan alt ajanının başlattığı komut, alt ajanın koşusu bitince durur.
            await asyncio.to_thread(job_lifetime.stop_group, context.job_group)
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
        if ok and getattr(outcome, "hit_step_limit", False):
            # Claude Code: maxTurns'e ulaşan çıktı kısmi işaretlenir ve sürdürülebilir (#36).
            status = "partial"
            text = f"{PARTIAL_PREFIX}\n{text}"
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
    from .loop import AgentOutcome as _Outcome

    is_fork = (
        subtask.inherit_context and deps.config.runtime.subagent_context_mode != "evidence_bundle"
    )
    from .agent_runtime_hooks import scoped_hooks

    try:
        team_settings.validate_agent_hooks(persona)
        selected_model = deps.active_model_override or deps.config.agent
        if not is_fork:
            selected_model = (
                team_settings.child_model(
                    persona,
                    selected_model,
                    candidates=deps.config.candidates,
                    launch=deps.config.agent_launch,
                    invocation_model=subtask.model,
                )
                or selected_model
            )
    except ConfigError as error:
        return _Outcome(final_text=str(error), messages=[], tool_calls_made=0, ok=False)
    policy_parent = dataclasses.replace(deps, active_model_override=selected_model)
    # Tanımdaki `memory` alanı: ajana özel MEMORY.md (P-055, #24); dizin dosya araçlarına açılır.
    child_memory = team_settings.child_memory(deps, persona)
    context = team_settings.with_memory_roots(context, child_memory)
    label = team_settings.agent_label(persona, sub_id)
    policy, policy_factory = team_settings.child_policies(policy_parent, persona, label)
    sub_deps = _Deps(
        config=team_settings.child_config(deps.config, persona),
        active_model_override=selected_model,
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
        # Torun, bu ajan için matrisle seçilmiş güncel kipi temel alır.
        approval_mode=team_settings.child_approval_mode(policy_parent, persona),
        policy_for_mode=getattr(deps, "policy_for_mode", None),
        plain_memory=child_memory,
        prompt_cache_ttl=persona.cache_ttl,
        # Belleği olan ajan derslerini de kendine ayırır; olmayan ortak havuza yazar (P-055).
        lesson_owner=persona.name if persona.memory_scope else "",
        effect_recorder=deps.effect_recorder,
        lesson_context=deps.lesson_context,
        invocation_budget=deps.invocation_budget,
        clock=deps.clock,
        ancestor_mutation_barrier=deps.mutation_blocked_by_pending_input,
        # Kancalar (P-009) alt ajanda da çalışır; `SubagentStop` eşleştiricisi türe bakar.
        hooks=scoped_hooks(deps, persona, child=True, identifier=sub_id),
        agent_type=persona.name,
        home=deps.home,
        omit_initial_instructions=persona.omit_initial_instructions and not is_fork,
        include_external_memory=is_fork,
        allowed_agent_types=deps.allowed_agent_types,
        runtime_parent_session=deps.conversation_id or deps.child_runs.session_id,
        runtime_agent_id=sub_id,
        omit_git_snapshot=is_fork
        or (persona.source == "fusion" and persona.name in {"explore", "plan"}),
        permission_rules=deps.permission_rules,
        steering=deps.child_runs.message_queue(sub_id) if subtask.agent_id else None,
        mcp_connector=deps.mcp_connector,
        attempt_id=deps.trace_id_factory(),
        trace_id_factory=deps.trace_id_factory,
    )
    from .agent_runtime_hooks import child_mcp_scope

    async with AsyncExitStack() as lifetime:
        try:
            await lifetime.enter_async_context(child_mcp_scope(sub_deps, persona, subtask))
        except ConfigError:
            return _Outcome(
                final_text="Ajanın MCP bağlantısı kurulamadı; bağlantı ayarlarını denetleyin.",
                messages=[],
                tool_calls_made=0,
                ok=False,
            )
        available = build_agent_registry(sub_deps, depth=depth + 1, run_agent=run_agent).names()
        # Fork (P-054): ana geçmişin sistemsiz, kırpılmış görünümü alt ajanın başlangıcı olur.
        parent_messages = team_fork.parent_history(deps) if subtask.inherit_context else []
        inherited = team_fork.fork_history(parent_messages) if subtask.inherit_context else None
        parent_prompt = (
            parent_messages[0].content
            if parent_messages and parent_messages[0].role == "system"
            else None
        )
        from .evidence_handoff import compile_handoff

        if deps.config.runtime.subagent_context_mode == "evidence_bundle":
            inherited = None
        handoff = await asyncio.to_thread(
            compile_handoff,
            deps,
            _member_brief(
                persona if inherited is not None else dataclasses.replace(persona, prompt=""),
                subtask,
                skills=team_settings.preloaded_skills(deps, persona),
                fork_note=team_fork.FORK_BRIEF if inherited is not None else "",
            ),
        )
        from .agent_runtime_records import child_journal, resumed_history
        from .approval import ApprovalMode

        if (
            sub_deps.approval_mode is not None and sub_deps.approval_mode() is ApprovalMode.PLAN
        ) or (sub_deps.execution is not None and not sub_deps.execution.allow_mutation):
            subtask = dataclasses.replace(subtask, read_only=True)
        effective_tools = _capped_tools(
            _allowed_tools(sub_deps, persona, subtask, available=available),
            subtask.tool_cap,
            available,
            deny=subtask.tool_deny,
        )
        if subtask.background and not is_fork:
            from .agent_runtime_context import background_tools

            effective_tools = background_tools(sub_deps, effective_tools, available)
        if not is_fork:
            from .agent_runtime_context import sibling_roster

            roster = sibling_roster(deps, sub_id, effective_tools, available)
            handoff = "\n\n".join(part for part in (handoff, roster) if part)
        subtask = dataclasses.replace(
            subtask, tool_cap=frozenset(effective_tools) if effective_tools is not None else None
        )
        if persona.auto_compact_window:
            from .context_budget import CHARS_PER_TOKEN_ESTIMATE, HISTORY_SHARE

            window_chars = round(
                persona.auto_compact_window * HISTORY_SHARE * CHARS_PER_TOKEN_ESTIMATE
            )
            learned = sub_deps.learned_compression_chars
            sub_deps.learned_compression_chars = (
                window_chars if learned is None else min(learned, window_chars)
            )
        sub_deps.journal = await child_journal(deps, subtask, persona, sub_id)
        if sub_deps.journal is not None:
            from ...memory.subagent_journal import AgentTranscript, agent_lease
            from ...memory.turn_journal import FileTurnJournal

            assert isinstance(sub_deps.journal, FileTurnJournal)
            await lifetime.enter_async_context(agent_lease(sub_deps.journal))
            saved = deps.child_runs.record(sub_id)
            sub_deps.agent_transcript = AgentTranscript(
                sub_deps.journal,
                history=deps.child_runs.history(sub_id),
                complete_history=bool(saved and saved.complete_history)
                if subtask.resume
                else not subtask.inherit_context,
            )
        if subtask.resume:
            inherited = resumed_history(deps, sub_id)
            if saved is not None and not saved.complete_history:
                from ...core.types import Message

                inherited.append(
                    Message(
                        "user",
                        "Devam kaydı eksiksiz özgün geçmiş değildir; "
                        "yalnız saklanmış bağlam kullanılabilir.",
                        harness_note=True,
                    )
                )
            parent_prompt = (
                inherited[0].content if inherited and inherited[0].role == "system" else None
            )
        sub_deps.original_cursor.excluded_call_ids = frozenset(
            call.id for message in inherited or () for call in message.tool_calls
        )
        if sub_deps.hooks is not None:
            from ...core.hooks.events import HookEvent

            gate = await sub_deps.hooks.emit(
                HookEvent.SUBAGENT_START,
                subjects=(persona.name,),
                fields={"agent_id": sub_id, "agent_type": persona.name},
            )
            if gate.blocked or gate.halt:
                return _Outcome(
                    final_text=gate.reason
                    or gate.stop_reason
                    or "Alt ajan başlangıç kancası engelledi.",
                    messages=[],
                    ok=False,
                )
            handoff = "\n\n".join(part for part in (handoff, gate.context_text) if part)
        try:
            outcome = await run_agent(
                subtask.task,
                sub_deps,
                history=inherited,
                depth=depth + 1,
                self_review=False,
                extra_system=handoff,
                system_prompt=parent_prompt if inherited is not None else persona.prompt.strip(),
                allowed_tools=effective_tools,
                step_limit=child_step_limit(
                    deps, depth, requested=_min_limit(persona.max_turns or None, subtask.step_limit)
                ),
                images=subtask.images,
            )
            if sub_deps.agent_transcript is not None and isinstance(
                sub_deps.journal, FileTurnJournal
            ):
                state = sub_deps.journal.agent_state
                if state is not None:
                    deps.child_runs.remember(state, tuple(outcome.messages))
            from .agent_runtime_records import remember_outcome

            await remember_outcome(deps, subtask, persona, sub_id, outcome)
            return outcome
        finally:
            if sub_deps.agent_transcript is not None and isinstance(
                sub_deps.journal, FileTurnJournal
            ):
                state = sub_deps.journal.agent_state
                cached = deps.child_runs.record(sub_id)
                if state is not None and cached is not None and cached.status == "running":
                    deps.child_runs.remember(state, sub_deps.agent_transcript.messages)
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
    """`izolasyon: "worktree"` ise üyeye `.claude/worktrees/ajan-<kimlik>` ağacı aç.

    Ağaç oturumun KENDİ kökünün HEAD'inden dallanır (oturum bir ağaçtaysa o dalından).
    Üye bitince `_settle_worktree` karar verir: iş kaldıysa ağaç kalır, kalmadıysa
    kaldırılır. Salt okuyan üye için ağaç açılmaz.
    """
    if subtask.isolation != "worktree" or subtask.read_only:
        return None
    name = "ajan-" + re.sub(r"[^A-Za-z0-9._-]", "-", sub_id)[:48]
    return await asyncio.to_thread(enter_configured_worktree, context.root, name)


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


def spawn_agent_tool(
    deps: AgentDeps,
    *,
    depth: int,
    run_agent: RunAgent,
    canonical: bool = False,
    legacy_name: str = "",
) -> Tool:
    """Tek bir alt görevi bir ekip üyesine devreden araç."""

    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        if legacy_name:
            _LOG.warning("Task eski araç adıdır; yeni çağrılarda Agent kullanın.")
        if not canonical:
            _LOG.warning("spawn_agent eski araç adıdır; yeni çağrılarda Agent kullanın.")
        subtask = _parse_subtask(args)
        if isinstance(subtask, str):
            return ToolResult.failure(subtask)
        if depth_limit_reached(deps, depth):
            return ToolResult.failure(DEPTH_LIMIT_MESSAGE)
        if canonical:
            from .agent_runtime_tools import launch_agent

            return await launch_agent(deps, subtask, args, depth=depth, run_agent=run_agent)
        from .agent_runtime_context import launch_denial

        denial = launch_denial(
            deps, resolve_persona(deps.capabilities, subtask.persona), subtask.persona
        )
        if denial:
            return ToolResult.failure(denial)
        if _parse_true(args.get("run_in_background", args.get("arka_plan"))):
            from .agent_runtime_tools import legacy_background

            return await legacy_background(deps, subtask, depth=depth, run_agent=run_agent)
        run = await run_subagent(deps, subtask, depth=depth, run_agent=run_agent)
        return ToolResult(_cap_report(run.text), ok=run.ok)

    return Tool(
        name=legacy_name or ("Agent" if canonical else "spawn_agent"),
        description="Odaklı bir ALT-GÖREVİ temiz bağlamlı bir alt ajana devret; ajan işi "
        "kendi araçlarıyla yapıp sonucunu döner. Birden çok bağımsız iş varsa aynı yanıtta "
        "birden çok Agent çağrısı yap. Basit işlerde kullanma.",
        parameters=_AGENT_PARAMETERS if canonical else _LEGACY_SPAWN_PARAMETERS,
        run=_run,
    )


#: Claude Code `Agent` aracının parametreleri; eski Türkçe alanlar (`uzman`, `salt_okunur`,
#: `yazma_alani`, `baglam_miras`, `izolasyon`, `arka_plan`, `resume`) şemada yok ama gelen
#: çağrıda okunmaya devam eder.
_AGENT_PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "description": {**_STRING, "description": "Görevin kısa (3-5 sözcük) açıklaması."},
        "prompt": {**_STRING, "description": "Alt ajanın yapacağı görevin tam metni."},
        "subagent_type": {**_STRING, "description": "Kullanılacak ajan tanımının adı."},
        "model": {
            **_STRING,
            "description": "İsteğe bağlı model: sonnet, opus, haiku, inherit ya da tam kimlik.",
        },
        "name": {**_STRING, "description": "SendMessage ile ulaşmak için ajana verilen ad."},
        "isolation": {
            "type": "string",
            "enum": ["worktree"],
            "description": "worktree ise ajan geçici bir git çalışma ağacında koşar.",
        },
        "effort": {
            "type": "string",
            "enum": ["low", "medium", "high", "xhigh", "max"],
            "description": "Bu alt ajanın düşünme yoğunluğu; tanımdaki effort'u ezer.",
        },
        "run_in_background": {
            "type": "boolean",
            "description": "false ise sonuç beklenir; varsayılan arka plandır.",
        },
    },
    "required": ["prompt"],
}

_LEGACY_SPAWN_PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        **_SUBTASK_PROPERTIES,
        "arka_plan": {"type": "boolean"},
        **_AGENT_PARAMETERS["properties"],  # type: ignore[dict-item]
        "resume": _STRING,
    },
    "required": ["task"],
}


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
    task = args.get("prompt", args.get("task"))
    if not isinstance(task, str) or not task.strip():
        return "'task' alanı boş olmayan bir metin olmalı."
    persona = args.get("subagent_type", args.get("uzman", ""))
    scope = args.get("yazma_alani", ())
    if not isinstance(scope, (list, tuple)) or not all(isinstance(item, str) for item in scope):
        return "'yazma_alani' metin listesi olmalı."
    isolation = args.get("isolation", args.get("izolasyon", ""))
    if isolation and isolation != "worktree":
        return "'izolasyon' yalnız 'worktree' olabilir."
    return SubTask(
        task=task.strip(),
        model=str(args.get("model") or ""),
        name=str(args.get("name") or ""),
        resume=str(args.get("resume") or ""),
        effort=str(args.get("effort") or "").strip().lower(),
        persona=persona if isinstance(persona, str) else "",
        read_only=_parse_read_only(args.get("salt_okunur")),
        write_scope=tuple(item.strip() for item in scope if item.strip()),
        inherit_context=persona == "fork" or _parse_true(args.get("baglam_miras")),
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

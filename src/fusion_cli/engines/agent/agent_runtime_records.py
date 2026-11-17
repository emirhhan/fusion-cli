"""Ajan devam kaydını mevcut sahip ve günlük kapsamıyla çöz."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.agent_runtime_state import AgentRunState
from ...core.tools import ToolContext
from ...core.types import Message
from ...memory.subagent_journal import agent_journal, load_agent

if TYPE_CHECKING:
    from ...memory.turn_journal import FileTurnJournal
    from .loop import AgentDeps, AgentOutcome
    from .team import Persona, SubTask


def _session(deps: AgentDeps) -> str:
    return deps.conversation_id or deps.child_runs.session_id


def _state(
    deps: AgentDeps,
    task: SubTask,
    persona: Persona,
    identifier: str,
    *,
    context: ToolContext | None = None,
) -> AgentRunState:
    from .team_scope import derive_sub_context

    if context is None:
        context = resumed_context(derive_sub_context(deps.tool_context, task), task)
    return AgentRunState(
        identifier,
        _session(deps),
        str(deps.tool_context.root.resolve()),
        "fork" if task.persona == "fork" else persona.name,
        complete_history=False,
        name=task.name,
        status="running",
        tool_names=tuple(sorted(task.tool_cap)) if task.tool_cap is not None else None,
        denied_tools=tuple(sorted(task.tool_deny)),
        write_scope=tuple(str(path.resolve()) for path in context.write_scope)
        if context.write_scope is not None
        else None,
        read_only=task.read_only,
        background=task.background,
        parent_turn=deps.child_runs.current_turn or deps.attempt_id or "",
    )


async def child_journal(
    deps: AgentDeps,
    task: SubTask,
    persona: Persona,
    identifier: str,
    *,
    context: ToolContext,
) -> FileTurnJournal | None:
    if not task.agent_id or _one_shot(persona):
        return None
    fresh = _state(deps, task, persona, identifier, context=context)
    previous = deps.child_runs.record(identifier)
    state = replace(fresh, complete_history=bool(previous and previous.complete_history))
    deps.child_runs.remember(state, deps.child_runs.history(identifier))
    journal = await asyncio.to_thread(
        agent_journal,
        deps.config.memory_dir,
        deps.tool_context.root,
        _session(deps),
        identifier,
        state=state,
    )

    async def write_state(updated: AgentRunState) -> None:
        journal.agent_state = updated
        await asyncio.to_thread(journal.save, deps.child_runs.history(identifier))

    deps.child_runs.bind_writer(identifier, write_state)
    return journal


def resumed_history(deps: AgentDeps, identifier: str) -> list[Message]:
    return list(deps.child_runs.history(identifier))


async def remember_outcome(
    deps: AgentDeps, task: SubTask, persona: Persona, identifier: str, outcome: AgentOutcome
) -> None:
    if not task.agent_id or _one_shot(persona):
        return
    previous = deps.child_runs.record(identifier)
    state = replace(
        previous or _state(deps, task, persona, identifier),
        status="completed" if outcome.ok else "stopped",
    )
    deps.child_runs.remember(state, tuple(outcome.messages))
    journal = await asyncio.to_thread(
        agent_journal,
        deps.config.memory_dir,
        deps.tool_context.root,
        _session(deps),
        identifier,
        state=state,
    )
    await asyncio.to_thread(journal.save, outcome.messages)


def _one_shot(persona: Persona) -> bool:
    return persona.source == "fusion" and persona.name in {"explore", "plan"}


async def _resolve(deps: AgentDeps, target: str) -> AgentRunState:
    if not target.strip():
        raise ValueError("Ajan hedefi boş olamaz.")
    local = [
        state
        for state in deps.child_runs.records()
        if target == state.agent_id or (state.name and target == state.name)
    ]
    if len(local) > 1:
        raise ValueError("Ajan adı belirsiz; kimliği kullanın.")
    state = local[0] if local else None
    if state is None:
        entry = await asyncio.to_thread(
            load_agent, deps.config.memory_dir, deps.tool_context.root, _session(deps), target
        )
        if entry is not None and entry.agent_state is not None:
            state = entry.agent_state
            deps.child_runs.remember(state, entry.messages)
    if state is None:
        raise ValueError("Bu proje ve üst oturum için devam edilebilir ajan bulunamadı.")
    if state.parent_session != _session(deps) or state.root != str(
        deps.tool_context.root.resolve()
    ):
        raise ValueError("Ajan başka proje veya oturuma ait.")
    if state.status == "running" and not deps.child_runs.running(state.agent_id):
        raise ValueError("Kaydın son çalışma durumu doğrulanamıyor; yeni görev başlatın.")
    if state.status == "cancelled":
        raise ValueError("Kullanıcının iptal ettiği ajan devam ettirilemez.")
    return state


async def _resume_task(deps: AgentDeps, task: SubTask) -> SubTask:
    state = await _resolve(deps, task.resume)
    if deps.child_runs.running(state.agent_id):
        raise ValueError("Ajan hâlâ çalışıyor; tamamlanmasını bekleyin.")
    if not state.effective_write_scope:
        raise ValueError("Kayıtlı etkin yazma sınırı doğrulanamıyor; yeni görev başlatın.")
    saved = frozenset(state.tool_names) if state.tool_names is not None else None
    cap = (
        saved
        if task.tool_cap is None
        else task.tool_cap
        if saved is None
        else saved & task.tool_cap
    )
    return replace(
        task,
        agent_id=state.agent_id,
        persona=state.agent_type,
        name=state.name,
        resume_write_scope=state.write_scope,
        tool_cap=cap,
        read_only=task.read_only or state.read_only,
        background=state.background,
        tool_deny=task.tool_deny | frozenset(state.denied_tools),
    )


def resumed_context(context: ToolContext, task: SubTask) -> ToolContext:
    """Kayıt, güncel üst ve yeni istek sınırlarının yalnız kesişimini kullan."""
    if not task.resume:
        return context
    scope = (
        tuple(path.resolve() for path in context.write_scope)
        if context.write_scope is not None
        else None
    )
    requested = tuple((context.root / raw).resolve() for raw in task.write_scope)
    saved = task.resume_write_scope
    for boundary in (
        None if saved is None else tuple(Path(raw).resolve() for raw in saved),
        requested or None,
    ):
        if boundary is None:
            continue
        if scope is None:
            scope = boundary
            continue
        scope = tuple(
            dict.fromkeys(
                left if left.is_relative_to(right) else right
                for left in scope
                for right in boundary
                if left.is_relative_to(right) or right.is_relative_to(left)
            )
        )
    return replace(context, write_scope=scope)


def message_owner(deps: AgentDeps) -> AgentDeps:
    """Kardeş teslimini gönderenin doğrulanmış üst oturumuna bağla."""
    if not deps.runtime_agent_id:
        return deps
    sender = deps.child_runs.record(deps.runtime_agent_id)
    expected = {f"{deps.runtime_parent_session}/{deps.runtime_agent_id}"}
    if deps.runtime_parent_session == deps.child_runs.session_id:
        expected.add(deps.runtime_agent_id)
    if (
        sender is None
        or sender.root != str(deps.tool_context.root.resolve())
        or sender.parent_session != deps.runtime_parent_session
        or deps.conversation_id not in expected
    ):
        raise ValueError("Gönderen ajanın üst oturumu doğrulanamadı.")
    return replace(deps, conversation_id=sender.parent_session)

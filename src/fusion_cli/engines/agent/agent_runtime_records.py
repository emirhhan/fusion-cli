"""Ajan devam kaydını mevcut sahip ve günlük kapsamıyla çöz."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING

from ...core.agent_runtime_state import AgentRunState
from ...core.types import Message
from ...memory.subagent_journal import agent_journal, load_agent

if TYPE_CHECKING:
    from ...memory.turn_journal import FileTurnJournal
    from .loop import AgentDeps, AgentOutcome
    from .team import Persona, SubTask


def _session(deps: AgentDeps) -> str:
    return deps.conversation_id or deps.child_runs.session_id


def _state(deps: AgentDeps, task: SubTask, persona: Persona, identifier: str) -> AgentRunState:
    return AgentRunState(
        identifier,
        _session(deps),
        str(deps.tool_context.root.resolve()),
        task.persona or persona.name,
        complete_history=False,
        name=task.name,
        status="running",
        tool_names=tuple(sorted(task.tool_cap)) if task.tool_cap is not None else None,
        denied_tools=tuple(sorted(task.tool_deny)),
        write_scope=task.write_scope,
        read_only=task.read_only,
        background=task.background,
        parent_turn=deps.child_runs.current_turn or deps.attempt_id or "",
    )


async def child_journal(
    deps: AgentDeps, task: SubTask, persona: Persona, identifier: str
) -> FileTurnJournal | None:
    if not task.agent_id or _one_shot(persona):
        return None
    fresh = _state(deps, task, persona, identifier)
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
    local = [state for state in deps.child_runs.records() if target in {state.agent_id, state.name}]
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
        write_scope=state.write_scope,
        tool_cap=cap,
        read_only=task.read_only or state.read_only,
        background=state.background,
        tool_deny=task.tool_deny | frozenset(state.denied_tools),
    )

"""Agent ve SendMessage çağrılarını mevcut görev sahibine ve günlüğe bağlar."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from .agent_runtime_records import _one_shot, _resolve, _resume_task, _session, _state

if TYPE_CHECKING:
    from .loop import AgentDeps
    from .team import RunAgent, SubTask


def _receipt(
    status: str,
    identifier: str,
    content: str = "",
    *,
    complete: bool = False,
    deps: AgentDeps | None = None,
) -> ToolResult:
    from ...memory.subagent_journal import agent_journal

    path = (
        str(
            agent_journal(
                deps.config.memory_dir, deps.tool_context.root, _session(deps), identifier
            ).path
        )
        if deps is not None and identifier
        else ""
    )
    return ToolResult(
        json.dumps(
            {
                "transcriptPath": path,
                "transcriptFormat": "saved-known-history-json",
                "status": status,
                "agentId": identifier,
                "content": content,
                "completeHistory": complete,
            },
            ensure_ascii=False,
        )
    )


async def launch_agent(
    deps: AgentDeps, task: SubTask, args: ToolArgs, *, depth: int, run_agent: RunAgent
) -> ToolResult:
    from .team import (
        concurrent_limit,
        concurrent_limit_reached,
        new_agent_id,
        resolve_persona,
        run_subagent,
        subagent_budget_exhausted,
    )

    try:
        if task.persona == "fork" and (depth > 0 or not deps.config.agent_launch.fork_enabled):
            return ToolResult.failure("Modelin fork başlatması bu turda kapalı.")
        if task.resume:
            task = await _resume_task(deps, task)
        persona = resolve_persona(deps.capabilities, task.persona)
        from .agent_runtime_context import launch_denial

        denial = launch_denial(deps, persona, task.persona)
        if denial:
            return ToolResult.failure(denial)
        budget = subagent_budget_exhausted(deps)
        if budget:
            return ToolResult.failure(budget)
        if not task.resume:
            concurrent = concurrent_limit_reached(deps)
            if concurrent:
                return ToolResult.failure(concurrent)
        identifier = task.agent_id or new_agent_id(persona.name)
        task = replace(task, agent_id=identifier)
        if not _one_shot(persona) and not task.resume:
            deps.child_runs.remember(_state(deps, task, persona, identifier), ())
        background = persona.background or args.get("run_in_background", True) is not False
        if deps.interactive and deps.config.agent_launch.fork_enabled:
            background = True
        background = background and not deps.config.agent_launch.disable_background_tasks
        background = background and deps.config.runtime.background_agents and not _one_shot(persona)
        if not task.resume:
            task = replace(task, background=background)
            if not _one_shot(persona):
                deps.child_runs.remember(_state(deps, task, persona, identifier), ())
        if background:
            deps.child_runs.launch(
                identifier,
                _owned_background(replace(deps), task, depth=depth, run_agent=run_agent),
                max_parallel=concurrent_limit(deps),
            )
            return _receipt("async_launched", identifier, deps=deps)
        result = await run_subagent(deps, task, depth=depth, run_agent=run_agent)
        state = deps.child_runs.record(identifier)
        if not result.ok:
            return ToolResult.failure(result.text)
        return _receipt(
            "partial" if result.status == "partial" else "completed",
            "" if _one_shot(persona) else identifier,
            result.text,
            complete=bool(state and state.complete_history),
            deps=deps,
        )
    except (ValueError, OSError) as error:
        return ToolResult.failure(f"Ajan devam kaydı açılamadı ({type(error).__name__}).")


def runtime_tools(deps: AgentDeps, *, depth: int, run_agent: RunAgent) -> tuple[Tool, ...]:

    schema = {
        "type": "object",
        "properties": {"to": {"type": "string"}, "message": {"type": "string"}},
        "required": ["to", "message"],
    }
    return (
        Tool(
            name="SendMessage",
            description="Bu oturumun tamamlanmış alt ajanına devam mesajı gönder.",
            parameters=schema,
            run=partial(_send_message, deps=deps, depth=depth, run_agent=run_agent),
            mutating=True,
        ),
        Tool(
            name="ListAgents",
            description="Bu oturumun alt ajanlarını listele.",
            parameters={"type": "object", "properties": {"id": {"type": "string"}}},
            run=partial(_list_agents, deps=deps),
        ),
        Tool(
            name="TaskStop",
            description="Sahipli alt ajan görevini durdur.",
            parameters={
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
            run=partial(_stop_agent, deps=deps),
            mutating=True,
        ),
    )


async def legacy_background(
    deps: AgentDeps, task: SubTask, *, depth: int, run_agent: RunAgent
) -> ToolResult:
    """Eski araç adının metin makbuzu; yürütücü canonical Agent ile aynıdır."""
    from ...core.background_tasks import WORKER_CONVERSATION_PREFIX
    from ...core.errors import PathAccessError
    from .team_scope import derive_sub_context

    if depth > 0 or deps.conversation_id.startswith(WORKER_CONVERSATION_PREFIX):
        return ToolResult.failure("Alt ajan veya ayrı işçi yeni arka plan görevi açamaz.")
    if not deps.config.runtime.background_agents:
        return ToolResult.failure("Arka plan ajanları kapalı.")
    try:
        derive_sub_context(deps.tool_context, task)
    except PathAccessError:
        return ToolResult.failure("Yazma alanı üst görevin sınırları dışında.")
    result = await launch_agent(
        deps, task, {"run_in_background": True}, depth=depth, run_agent=run_agent
    )
    if not result.ok:
        return result
    receipt = json.loads(result.output)
    delivery = (
        "Sonuç sonraki sohbet turuna iletilir."
        if deps.child_runs.persistent
        else "Sonuç kendiliğinden gelmez, görev sahibi tamamlanmayı bekler."
    )
    return ToolResult(
        f"Arka plan ajanı: {receipt['agentId']}. Durumu list_agents ile izleyebilirsin. {delivery}"
    )


async def _owned_background(
    deps: AgentDeps, task: SubTask, *, depth: int, run_agent: RunAgent
) -> object:
    from .team import run_subagent

    result = await run_subagent(deps, task, depth=depth, run_agent=run_agent)
    state = deps.child_runs.record(task.agent_id)
    if state is not None:
        await deps.child_runs.set_status(
            task.agent_id, result.status or ("completed" if result.ok else "failed")
        )
    deps.child_runs.completed(task.agent_id, result.text)
    return result


async def _send_message(
    args: ToolArgs, context: ToolContext, *, deps: AgentDeps, depth: int, run_agent: RunAgent
) -> ToolResult:
    from .team import DEPTH_LIMIT_MESSAGE, SubTask, depth_limit_reached

    if depth_limit_reached(deps, depth):
        return ToolResult.failure(DEPTH_LIMIT_MESSAGE)
    target, message = args.get("to"), args.get("message")
    if (
        not isinstance(target, str)
        or not isinstance(message, str)
        or not target.strip()
        or not message.strip()
    ):
        return ToolResult.failure("to ve message dolu metin olmalı.")
    try:
        state = await _resolve(deps, target)
        from .agent_runtime_context import launch_denial
        from .team import resolve_persona

        denial = launch_denial(
            deps, resolve_persona(deps.capabilities, state.agent_type), state.agent_type
        )
        if denial:
            return ToolResult.failure(denial)
        if deps.child_runs.running(state.agent_id):
            deps.child_runs.message_queue(state.agent_id).push(message)
            return _receipt("message_delivered", state.agent_id, deps=deps)
    except (ValueError, OSError):
        return ToolResult.failure("Bu oturuma ait ajan bulunamadı.")
    return await launch_agent(
        deps,
        SubTask(message, resume=target),
        {"run_in_background": True},
        depth=depth,
        run_agent=run_agent,
    )


async def _list_agents(args: ToolArgs, context: ToolContext, *, deps: AgentDeps) -> ToolResult:
    target = args.get("id")
    if isinstance(target, str) and target:
        try:
            state = await _resolve(deps, target)
            content = next(
                (
                    message.content
                    for message in reversed(deps.child_runs.history(state.agent_id))
                    if message.role == "assistant" and not message.tool_calls
                ),
                "",
            )
            return _receipt(
                state.status, state.agent_id, content, complete=state.complete_history, deps=deps
            )
        except (ValueError, OSError):
            return ToolResult.failure("Bu oturuma ait ajan bulunamadı.")
    states = [
        state
        for state in deps.child_runs.records()
        if state.parent_session == _session(deps) and state.root == str(context.root.resolve())
    ]
    return ToolResult(
        json.dumps(
            [
                {"agentId": state.agent_id, "name": state.name, "status": state.status}
                for state in states
            ],
            ensure_ascii=False,
        )
    )


async def _stop_agent(args: ToolArgs, context: ToolContext, *, deps: AgentDeps) -> ToolResult:
    try:
        state = await _resolve(deps, str(args.get("task_id") or args.get("id") or ""))
        await deps.child_runs.cancel(state.agent_id)
        await deps.child_runs.set_status(state.agent_id, "stopped")
        return _receipt("stopped", state.agent_id, deps=deps)
    except ValueError:
        return ToolResult.failure("Durdurulabilir ajan bulunamadı.")

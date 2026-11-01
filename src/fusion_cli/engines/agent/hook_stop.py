"""Stop / SubagentStop kancaları: tur sonunda ajanı gerekçeyle sürdürme (Claude Code kuralı).

Engel (`decision: block` / çıkış 2) ya da `hookSpecificOutput.additionalContext` turu
sürdürür; ikincisi hata göstermez ("Stop hook feedback"). Art arda en çok 8 sürdürme
(`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` ile değişir); ajan araç çağırınca sayaç sıfırlanır,
tavan dolunca sonraki engel yok sayılır ve tur biter. Modele yalnız gerekçe gider.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, TypeVar

from ...config.hooks import stop_hook_block_cap
from ...core.hooks.events import HookEvent
from ...core.types import Message
from . import hook_text
from .hook_bridge import HOOK_TOOL_OUTPUT_CHARS, publish_verdict, session_of

if TYPE_CHECKING:
    from .loop import AgentDeps


async def stop_continuation(
    deps: AgentDeps, final_text: str, *, subagent: bool, continuations: int
) -> str | None:
    """Stop/SubagentStop engellediyse ajanın sürdüreceği istem; durabilirse `None`."""
    session = session_of(deps)
    if session is None:
        return None
    event = HookEvent.SUBAGENT_STOP if subagent else HookEvent.STOP
    agent_type = str(getattr(deps, "agent_type", "") or "")
    fields: dict[str, object] = {
        "stop_hook_active": continuations > 0,
        "last_assistant_message": final_text[:HOOK_TOOL_OUTPUT_CHARS],
        "background_tasks": _background_tasks(deps),
        "session_crons": _session_crons(deps),
    }
    if subagent:
        fields["agent_type"] = agent_type
        fields["agent_id"] = deps.runtime_agent_id
        from ...memory.turn_journal import FileTurnJournal

        if isinstance(deps.journal, FileTurnJournal) and deps.journal.path.is_file():
            fields["agent_transcript_path"] = str(deps.journal.path)
    else:
        session.record("assistant", final_text)
    verdict = await session.emit(event, subjects=(agent_type,), fields=fields)
    publish_verdict(deps.publisher, verdict)
    if verdict.halt:
        return None
    if verdict.blocked:
        return verdict.reason or event.value
    if verdict.context_text:
        return hook_text.stop_feedback(verdict.context_text)
    return None


def _background_tasks(deps: AgentDeps) -> list[dict[str, object]]:
    """Süren arka plan işleri (alt ajanlar): kimlik + tür."""
    runs = getattr(deps, "child_runs", None)
    if runs is None:
        return []
    tasks = {**getattr(runs, "_tasks", {}), **getattr(runs, "_background", {})}
    return [
        {"id": str(identifier), "type": "subagent"}
        for identifier, task in tasks.items()
        if task is not None and not task.done()
    ]


def _session_crons(deps: AgentDeps) -> list[dict[str, object]]:
    """Oturumun zamanlanmış uyandırmaları (`SessionCron`)."""
    cron = getattr(getattr(deps, "tool_context", None), "cron", None)
    listing = getattr(cron, "list", None)
    if not callable(listing):
        return []
    return [task.to_dict() for task in listing()]


class _Transcript(Protocol):
    final_text: str
    messages: list[Message]
    ok: bool
    budget_stopped: bool


OutcomeT = TypeVar("OutcomeT", bound=_Transcript)


async def continue_until_stop_allowed(
    deps: AgentDeps,
    outcome: OutcomeT,
    rerun: Callable[[str, list[Message]], Awaitable[OutcomeT]],
    *,
    subagent: bool,
) -> OutcomeT:
    """Stop kancası izin verene (ya da art arda sınır dolana) kadar turu sürdür.

    Yalnız temiz biten turda sorulur: bütçe/adım sınırı, model hatası, kullanıcı reddi ve
    kanca `continue: false` durdurmasında Stop tetiklenmez (Claude da kesintide ve sınır
    hatasında çalıştırmaz).
    """
    cap = stop_hook_block_cap()
    total = 0
    consecutive = 0
    while _ended_cleanly(deps, outcome):
        if subagent and deps.agent_transcript is not None:
            await deps.agent_transcript.capture(outcome.messages)
        prompt = await stop_continuation(
            deps, outcome.final_text, subagent=subagent, continuations=total
        )
        if prompt is None or consecutive >= cap:
            return outcome
        before = len(outcome.messages)
        outcome = await rerun(prompt, outcome.messages)
        total += 1
        consecutive = 0 if _called_tool(outcome.messages[before:]) else consecutive + 1
    return outcome


def _called_tool(new_messages: list[Message]) -> bool:
    return any(message.role == "tool" for message in new_messages)


def _ended_cleanly(deps: AgentDeps, outcome: _Transcript) -> bool:
    budget = getattr(deps, "budget", None)
    stopped = budget is not None and budget.stop is not None
    return outcome.ok and not outcome.budget_stopped and not stopped

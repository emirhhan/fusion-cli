"""`PostToolBatch` kancası: bir araç grubunun hepsi bitince, sonraki model çağrısından önce.

Claude Code gibi eşleştiricisi yoktur ve grup başına bir kez çalışır. Girdi
`tool_calls`: her çağrı için `tool_name`, `tool_input`, `tool_use_id` ve modelin gördüğü
`tool_response` metni. `additionalContext` sonraki model çağrısından önce bir kez
eklenir; `decision: "block"`, `continue: false` ya da çıkış 2 döngüyü durdurur ve
gerekçe uyarı olarak konuşmada kalır.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.budget import BudgetStop, TurnBudget
from ...core.hooks.events import HookEvent
from ...core.types import Message, ToolCall
from ...ui import messages as ui_messages
from . import hook_text
from .hook_bridge import _publish, session_of, tool_hook_fields

if TYPE_CHECKING:
    from .loop import AgentDeps

#: Modele giden yanıt metninin kanca girdisindeki üst sınırı (karakter).
BATCH_RESPONSE_CHARS = 20_000


@dataclass(frozen=True, slots=True)
class BatchGate:
    """Grup kararı: modele eklenecek not ve/veya turu durduran metin."""

    note: str = ""
    halt: str | None = None


def _arguments(call: ToolCall) -> dict[str, object]:
    try:
        parsed = json.loads(call.arguments or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def batch_entries(
    deps: AgentDeps, calls: Sequence[ToolCall], conversation: Sequence[Message]
) -> list[dict[str, object]]:
    """Gruptaki her çağrının Claude biçimli kaydı (yanıt, modele giden araç mesajı)."""
    session = session_of(deps)
    root = (session.project_dir or session.root) if session is not None else None
    responses = {m.tool_call_id: m.content for m in conversation if m.role == "tool"}
    entries: list[dict[str, object]] = []
    for call in calls:
        fields = tool_hook_fields(call.name, _arguments(call), call.id, root=root)
        entries.append(
            {
                "tool_name": fields["tool_name"],
                "tool_input": fields["tool_input"],
                "tool_use_id": call.id,
                "tool_response": str(responses.get(call.id, ""))[:BATCH_RESPONSE_CHARS],
            }
        )
    return entries


async def post_tool_batch(
    deps: AgentDeps, calls: Sequence[ToolCall], conversation: list[Message]
) -> BatchGate:
    """Grubu kancalara ver; bağlamı konuşmaya ekle, engelse durdurma metnini döndür."""
    session = session_of(deps)
    if session is None or not calls or not session.has(HookEvent.POST_TOOL_BATCH):
        return BatchGate()
    fields = {"tool_calls": batch_entries(deps, calls, conversation)}
    verdict = await session.emit(HookEvent.POST_TOOL_BATCH, fields=fields)
    _publish(deps, verdict)
    note = hook_text.context_reminder(HookEvent.POST_TOOL_BATCH, verdict.context_text)
    if note:
        conversation.append(Message("user", note, harness_note=True))
    if verdict.blocked or verdict.halt:
        reason = verdict.reason or verdict.stop_reason or ui_messages.HOOKS_NO_REASON
        halt = ui_messages.HOOKS_TURN_HALTED.format(
            event=HookEvent.POST_TOOL_BATCH.value, reason=reason
        )
        conversation.append(Message("user", halt, harness_note=True))
        return BatchGate(note, halt)
    return BatchGate(note)


async def batch_hook(
    deps: AgentDeps,
    calls: Sequence[ToolCall],
    conversation: list[Message],
    state: object,
    budget: TurnBudget,
) -> None:
    """Döngü bağlantısı: zaten durmuş turda çalışmaz; engel turu kullanıcı reddi gibi bitirir."""
    if budget.stop is not None:
        return
    gate = await post_tool_batch(deps, calls, conversation)
    if gate.halt is not None:
        setattr(state, "hook_halt", gate.halt)  # noqa: B010 - `_State` loop.py'de
        budget.halt(BudgetStop.USER_DENIED)

"""stream-json'da alt ajan mesajları ve `--forward-subagent-text` (#289).

Claude Code'da alt ajan mesajları akışa `assistant`/`user` olarak düşer; `parent_tool_use_id`
alanı mesajın hangi Agent çağrısına ait olduğunu söyler (ana konuşmada `null`). İlk mesaj
alt ajanı süren istemi taşıyan bir `user` mesajıdır; sonra varsayılan olarak yalnız
`tool_use`/`tool_result` blokları gelir. `--forward-subagent-text` ya da
`CLAUDE_CODE_FORWARD_SUBAGENT_TEXT` ile metin blokları da eklenir ve iç içe her derinlikteki
alt ajan iletilir (varsayılanda yalnız ana konuşmanın doğrudan çocukları).

Fusion'da alt ajan olayları `agent_id` ile işaretlenir; Agent çağrısı (`spawn_agent`,
`invoke_agent`) başlayınca kimliği sıraya alınır, ardından gelen `SubAgentStarted`
(aynı üst ajandan) bu çağrıya bağlanır. Paralel grup (`group_size`) aynı çağrıyı paylaşır.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from ..core.events import (
    Event,
    SubAgentFinished,
    SubAgentStarted,
    TokenReceived,
    ToolExecuted,
    ToolOutcome,
    ToolStarted,
)

FORWARD_TEXT_ENV = "CLAUDE_CODE_FORWARD_SUBAGENT_TEXT"
_AGENT_TOOLS = frozenset({"spawn_agent", "invoke_agent"})
_TRUE = frozenset({"1", "true", "yes", "on"})


def forward_text_enabled(flag: bool) -> bool:
    return flag or os.environ.get(FORWARD_TEXT_ENV, "").strip().lower() in _TRUE


@dataclass(slots=True)
class _Call:
    call_id: str
    claimed: int = 0


@dataclass(slots=True)
class _Sub:
    parent_tool_use_id: str
    depth: int
    text: str = ""


#: (içerik blokları, parent_tool_use_id) → mesaj yazan geri çağırımlar.
Emit = Callable[[list[dict[str, object]], str], None]


class SubagentForwarder:
    """Alt ajan olaylarını `parent_tool_use_id`'li SDK mesajlarına çevirir."""

    def __init__(self, *, assistant: Emit, user: Emit, forward_text: bool) -> None:
        self._assistant = assistant
        self._user = user
        self._forward_text = forward_text
        self._calls: dict[str, list[_Call]] = {}
        self._subs: dict[str, _Sub] = {}

    def observe(self, event: Event) -> bool:
        """Olayı işle; alt ajana aitse `True` (ana akış yazmasın)."""
        if isinstance(event, ToolStarted) and event.name in _AGENT_TOOLS and event.call_id:
            self._calls.setdefault(event.agent_id, []).append(_Call(event.call_id))
        if isinstance(event, SubAgentStarted):
            self._started(event)
            return bool(event.agent_id)
        if isinstance(event, SubAgentFinished):
            done = self._subs.pop(event.sub_id, None)
            if done is not None and self._visible(done):
                self._finished(event, done)
            return bool(event.agent_id)
        if not event.agent_id:
            return False
        sub = self._subs.get(event.agent_id)
        if sub is not None and self._visible(sub):
            self._forward(event, sub)
        return True

    def _visible(self, sub: _Sub) -> bool:
        return self._forward_text or sub.depth <= 1

    def _started(self, event: SubAgentStarted) -> None:
        queue = self._calls.get(event.agent_id) or []
        if not queue or not event.sub_id:
            return
        call = queue[0]
        call.claimed += 1
        if call.claimed >= max(1, event.group_size):
            queue.pop(0)
        sub = _Sub(call.call_id, max(1, event.depth))
        self._subs[event.sub_id] = sub
        if self._visible(sub) and event.task.strip():
            self._user([{"type": "text", "text": event.task}], sub.parent_tool_use_id)

    def _forward(self, event: Event, sub: _Sub) -> None:
        from .sdk_messages import claude_tool_name

        if isinstance(event, TokenReceived):
            if self._forward_text and event.provisional:
                sub.text += event.text
        elif isinstance(event, ToolStarted):
            content = self._flush(sub)
            content.append(
                {
                    "type": "tool_use",
                    "id": event.call_id or "",
                    "name": claude_tool_name(event.name),
                    "input": dict(event.args),
                }
            )
            self._assistant(content, sub.parent_tool_use_id)
        elif isinstance(event, ToolExecuted):
            block = {
                "type": "tool_result",
                "tool_use_id": event.call_id or "",
                "content": event.output,
                "is_error": event.outcome is not ToolOutcome.OK,
            }
            self._user([block], sub.parent_tool_use_id)

    def _finished(self, event: SubAgentFinished, sub: _Sub) -> None:
        content = self._flush(sub)
        if self._forward_text and not content and event.summary.strip():
            content = [{"type": "text", "text": event.summary.strip()}]
        if content:
            self._assistant(content, sub.parent_tool_use_id)

    def _flush(self, sub: _Sub) -> list[dict[str, object]]:
        text, sub.text = sub.text.strip(), ""
        return [{"type": "text", "text": text}] if text else []

"""Claude Agent SDK mesaj biçimi: `--output-format json|stream-json` (#279, #280, #284).

`json` tek bir `SDKResultMessage` nesnesi basar (`type`, `subtype`, `session_id`, `result`,
`is_error`, `num_turns`, `total_cost_usd`, `usage`, `modelUsage`, `permission_denials`,
`structured_output`…). `stream-json` her satıra bir SDK mesajı yazar: önce `system/init`,
sonra `assistant` (metin + `tool_use` blokları) ve `user` (`tool_result`) mesajları,
yeniden denemede `system/api_retry`, en sonda aynı `result` nesnesi.

Fusion'ın iç olayları bu biçime `SdkStream` dinleyicisinde çevrilir; Fusion'a özgü ek
bilgi (`maliyet_tam`, durma nedeni) sonuç nesnesinin `fusion` alt nesnesinde kalır.
"""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TextIO

from .. import __version__
from ..core.events import (
    Event,
    ExecutionRetryScheduled,
    ModelCallFinished,
    TokenReceived,
    ToolExecuted,
    ToolOutcome,
    ToolStarted,
)
from ..core.redaction import redact
from ..engines.agent.approval import ApprovalMode

#: Fusion araç adı → Claude araç adı (çıktıda Claude adları görünür).
_CLAUDE_NAMES = {
    "run_shell": "Bash",
    "read_file": "Read",
    "view_file": "Read",
    "write_file": "Write",
    "edit_file": "Edit",
    "multi_edit": "Edit",
    "grep_search": "Grep",
    "search_code": "Grep",
    "glob": "Glob",
    "list_dir": "LS",
    "web_search": "WebSearch",
    "web_fetch": "WebFetch",
    "read_url_content": "WebFetch",
    "ask_user": "AskUserQuestion",
    "todo_write": "TodoWrite",
    "spawn_agent": "Agent",
    "invoke_agent": "Agent",
    "read_skill": "Skill",
}
#: Fusion kipi → Claude `permissionMode` adı.
CLAUDE_MODE_NAMES = {
    ApprovalMode.AUTO: "auto",
    ApprovalMode.ACCEPT_EDITS: "acceptEdits",
    ApprovalMode.SECURITY: "default",
    ApprovalMode.PLAN: "plan",
    ApprovalMode.BYPASS: "bypassPermissions",
    ApprovalMode.DONT_ASK: "dontAsk",
}
SUBTYPE_SUCCESS = "success"
SUBTYPE_MAX_TURNS = "error_max_turns"
SUBTYPE_MAX_BUDGET = "error_max_budget_usd"
SUBTYPE_EXECUTION = "error_during_execution"
SUBTYPE_STRUCTURED = "error_max_structured_output_retries"


def claude_tool_name(name: str) -> str:
    if name in _CLAUDE_NAMES:
        return _CLAUDE_NAMES[name]
    if "__" in name and not name.startswith("mcp__"):
        return f"mcp__{name}"
    return name


def redacted(value: object) -> object:
    """Dize değerlerindeki sırları maskele; JSON yapısına (anahtarlara) dokunma."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, Mapping):
        return {key: redacted(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redacted(item) for item in value]
    return value


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass(slots=True)
class RunStats:
    """Sonuç nesnesi için tur boyunca toplanan ölçümler."""

    api_ms: int = 0
    model_usage: dict[str, dict[str, float | int]] = field(default_factory=dict)
    denials: list[dict[str, object]] = field(default_factory=list)

    def handle(self, event: Event) -> None:
        if isinstance(event, ModelCallFinished):
            self._record_call(event)
        elif (
            isinstance(event, ToolExecuted)
            and not event.agent_id
            and event.outcome in (ToolOutcome.DENIED, ToolOutcome.BLOCKED)
        ):
            self.denials.append(_denial(event))

    def _record_call(self, event: ModelCallFinished) -> None:
        result = event.result
        self.api_ms += max(0, int(result.latency_ms))
        row = self.model_usage.setdefault(
            result.model or event.requested_model or "unknown",
            {
                "inputTokens": 0,
                "outputTokens": 0,
                "cacheReadInputTokens": 0,
                "cacheCreationInputTokens": 0,
                "webSearchRequests": 0,
                "costUSD": 0.0,
            },
        )
        row["inputTokens"] = int(row["inputTokens"]) + result.usage.prompt_tokens
        row["outputTokens"] = int(row["outputTokens"]) + result.usage.completion_tokens
        row["costUSD"] = round(float(row["costUSD"]) + result.usage.cost_usd, 6)


def _denial(event: ToolExecuted) -> dict[str, object]:
    return {
        "tool_name": claude_tool_name(event.name),
        "tool_use_id": event.call_id or "",
        "tool_input": dict(event.args),
    }


@dataclass(frozen=True, slots=True)
class ResultInput:
    """`result_message` girdisi (komut gövdesinden toplanır)."""

    session_id: str
    final_text: str
    subtype: str
    num_turns: int
    duration_ms: int
    stop_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cost_complete: bool
    structured: object | None = None
    has_structured: bool = False
    errors: tuple[str, ...] = ()


def result_subtype(*, ok: bool, hit_turn_limit: bool, stop_reason: str | None) -> str:
    """Fusion sonucunu Claude alt türüne eşle (#279, #285)."""
    if ok:
        return SUBTYPE_SUCCESS
    if hit_turn_limit or stop_reason in ("step_limit", "max_model_calls", "model_calls"):
        return SUBTYPE_MAX_TURNS
    if stop_reason == "cost_limit":
        return SUBTYPE_MAX_BUDGET
    return SUBTYPE_EXECUTION


def result_message(data: ResultInput, stats: RunStats) -> dict[str, object]:
    """`SDKResultMessage` (tek satır)."""
    is_error = data.subtype != SUBTYPE_SUCCESS
    message: dict[str, object] = {
        "type": "result",
        "subtype": data.subtype,
        "is_error": is_error,
        "duration_ms": data.duration_ms,
        "duration_api_ms": stats.api_ms,
        "num_turns": data.num_turns,
        "session_id": data.session_id,
        "total_cost_usd": round(data.cost_usd, 6),
        "usage": {
            "input_tokens": data.prompt_tokens,
            "output_tokens": data.completion_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        "modelUsage": stats.model_usage,
        "permission_denials": list(stats.denials),
        "stop_reason": data.stop_reason,
        "uuid": _uuid(),
    }
    if is_error:
        message["errors"] = list(data.errors) or [redact(data.final_text)]
    else:
        message["result"] = redact(data.final_text)
    if data.has_structured:
        message["structured_output"] = data.structured
    message["fusion"] = {"maliyet_tam": data.cost_complete, "durma_nedeni": data.stop_reason}
    return message


def init_message(
    *,
    session_id: str,
    cwd: str,
    model: str,
    mode: ApprovalMode,
    mcp_servers: Sequence[str],
    mcp_errors: Sequence[Mapping[str, str]] = (),
    tools: Sequence[str] = (),
    agents: Sequence[str] = (),
) -> dict[str, object]:
    """`system/init` (stream-json'un ilk satırı)."""
    message: dict[str, object] = {
        "type": "system",
        "subtype": "init",
        "cwd": cwd,
        "session_id": session_id,
        "tools": [claude_tool_name(name) for name in tools],
        "mcp_servers": [{"name": name, "status": "pending"} for name in mcp_servers],
        "model": model,
        "permissionMode": CLAUDE_MODE_NAMES.get(mode, mode.value),
        "slash_commands": [],
        "apiKeySource": "none",
        "claude_code_version": __version__,
        "output_style": "default",
        "agents": list(agents),
        "skills": [],
        "plugins": [],
        "uuid": _uuid(),
    }
    if mcp_errors:
        message["mcp_server_errors"] = [dict(item) for item in mcp_errors]
    return message


def assistant_message(
    session_id: str, model: str, content: list[dict[str, object]], parent: str | None = None
) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
        "parent_tool_use_id": parent,
        "session_id": session_id,
        "uuid": _uuid(),
    }


def user_message(session_id: str, content: object, parent: str | None = None) -> dict[str, object]:
    return {
        "type": "user",
        "message": {"role": "user", "content": content},
        "parent_tool_use_id": parent,
        "session_id": session_id,
        "uuid": _uuid(),
    }


class SdkStream:
    """Fusion olaylarını satır satır SDK mesajına çeviren dinleyici (stream-json)."""

    def __init__(
        self,
        session_id: str,
        model: Callable[[], str],
        *,
        stdout: TextIO | None = None,
        partial: bool = False,
        forward_subagent_text: bool = False,
        include_hooks: bool = False,
        prompt_suggestions: bool = False,
    ) -> None:
        from .sdk_subagents import SubagentForwarder, forward_text_enabled
        from .sdk_suggestions import PromptSuggestions

        self.session_id = session_id
        self._model = model
        self._stdout = stdout or sys.stdout
        self._partial = partial
        self._pending_text = ""
        self._subagents = SubagentForwarder(
            assistant=lambda content, parent: self.write(
                assistant_message(self.session_id, self._model(), content, parent)
            ),
            user=lambda content, parent: self.write(user_message(self.session_id, content, parent)),
            forward_text=forward_text_enabled(forward_subagent_text),
        )
        self._suggestions = PromptSuggestions(self.write) if prompt_suggestions else None
        if include_hooks:
            from ..engines.hooks.lifecycle import add_observer

            add_observer(self.hook_event)

    def write(self, message: Mapping[str, object]) -> None:
        line = json.dumps(redacted(message), ensure_ascii=False, default=str)
        self._stdout.write(line + "\n")
        self._stdout.flush()

    def handle(self, event: Event) -> None:
        if self._subagents.observe(event):
            return
        if self._suggestions is not None:
            self._suggestions.observe(event)
        if isinstance(event, TokenReceived):
            self._token(event)
        elif isinstance(event, ToolStarted):
            self._tool_started(event)
        elif isinstance(event, ToolExecuted):
            self._tool_executed(event)
        elif isinstance(event, ExecutionRetryScheduled):
            self.write(
                {
                    "type": "system",
                    "subtype": "api_retry",
                    "attempt": event.attempt,
                    "error": event.reason,
                    "session_id": self.session_id,
                    "uuid": _uuid(),
                }
            )

    def hook_event(self, message: Mapping[str, object]) -> None:
        """`--include-hook-events` (#289): `system/hook_started` / `system/hook_response`."""
        self.write({"type": "system", **message, "session_id": self.session_id, "uuid": _uuid()})

    def after_result(self) -> None:
        """Sonuç mesajından sonra: `--prompt-suggestions` önerisi (#289)."""
        if self._suggestions is not None:
            self._suggestions.flush(self.session_id)

    def final_answer(self, text: str) -> None:
        """Turun kabul edilen cevabını `assistant` mesajı olarak yaz."""
        self._pending_text = ""
        if text.strip():
            self.write(
                assistant_message(self.session_id, self._model(), [{"type": "text", "text": text}])
            )

    def _token(self, event: TokenReceived) -> None:
        if event.provisional:
            self._pending_text += event.text
        if self._partial and event.text:
            self.write(
                {
                    "type": "stream_event",
                    "event": {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": event.text},
                    },
                    "parent_tool_use_id": None,
                    "session_id": self.session_id,
                    "uuid": _uuid(),
                }
            )

    def _tool_started(self, event: ToolStarted) -> None:
        content: list[dict[str, object]] = []
        if self._pending_text.strip():
            content.append({"type": "text", "text": self._pending_text.strip()})
        self._pending_text = ""
        content.append(
            {
                "type": "tool_use",
                "id": event.call_id or f"toolu_{uuid.uuid4().hex[:24]}",
                "name": claude_tool_name(event.name),
                "input": dict(event.args),
            }
        )
        self.write(assistant_message(self.session_id, self._model(), content))

    def _tool_executed(self, event: ToolExecuted) -> None:
        if event.outcome in (ToolOutcome.DENIED, ToolOutcome.BLOCKED):
            self.write(
                {
                    "type": "system",
                    "subtype": "permission_denied",
                    **_denial(event),
                    "session_id": self.session_id,
                    "uuid": _uuid(),
                }
            )
        block = {
            "type": "tool_result",
            "tool_use_id": event.call_id or "",
            "content": event.output,
            "is_error": event.outcome is not ToolOutcome.OK,
        }
        self.write(user_message(self.session_id, [block]))

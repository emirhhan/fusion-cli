"""Model geçmişini değiştirmeden görünür sohbet akışına dönüştürür."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from ..core.redaction import REDACTED_MARK, contains_sensitive, redact
from ..core.types import Message, ToolCall

# Yalnız bu araçlar eski günlüklerde gerçek unified diff sonucu üretirdi.
_LEGACY_DIFF_TOOLS = frozenset({"write_file", "edit_file", "multi_edit"})
_LEGACY_DIFF = re.compile(r"(?m)^--- a/[^\n]+\n\+\+\+ b/[^\n]+\n@@ [^\n]+ @@[^\n]*\n")


def _safe_value(value: object) -> object:
    """JSON yapısını koruyarak sır adlarını ve metin değerlerini temizler."""
    if isinstance(value, dict):
        return {
            redact(str(key)): REDACTED_MARK
            if contains_sensitive(f"{key}=deger")
            else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return redact(value) if isinstance(value, str) else value


#: Bundan derin iç içe argüman görünür geçmişe alınmaz. Python sürümüne göre değişen
#: özyineleme sınırına bırakılmaz: 3.12 sınırı gevşetti ve test sürümler arası ayrıştı.
MAX_ARGUMENT_DEPTH = 32


def _too_deep(value: object) -> bool:
    """İç içe derinliği özyinelemesiz ölç; sınırı aşan yapı reddedilir."""
    pending = [(value, 1)]
    while pending:
        current, depth = pending.pop()
        if depth > MAX_ARGUMENT_DEPTH:
            return True
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
    return False


def _arguments(call: ToolCall | None) -> dict[str, object]:
    if call is None:
        return {}
    try:
        parsed = json.loads(call.arguments)
        if not isinstance(parsed, dict) or _too_deep(parsed):
            return {}
        return {
            redact(str(key)): REDACTED_MARK
            if contains_sensitive(f"{key}=deger")
            else _safe_value(value)
            for key, value in parsed.items()
        }
    except (ValueError, TypeError, RecursionError):
        return {}


def _tool_row(message: Message, call: ToolCall | None) -> dict[str, object]:
    name = message.name or (call.name if call else "")
    diff = None
    if message.ok is True:
        diff = message.tool_diff
        if (
            diff is None
            and name in _LEGACY_DIFF_TOOLS
            and (match := _LEGACY_DIFF.search(message.content)) is not None
        ):
            diff = message.content[match.start() :]
    event: dict[str, object] = {
        "olay": "ToolExecuted",
        "name": redact(name),
        "args": _arguments(call),
        "outcome": "ok" if message.ok is True else "failed" if message.ok is False else "unknown",
        "output": redact(message.content),
        "diff": redact(diff) if diff is not None else None,
    }
    row: dict[str, object] = {"rol": "olay", "olay": event}
    if message.tool_call_id:
        row["id"] = message.tool_call_id
    return row


def visible_history(messages: Sequence[Message]) -> list[dict[str, object]]:
    """Araç sonuçlarını olay satırı olarak, anlatımları özgün sırada sunar."""
    rows: list[dict[str, object]] = []
    calls: dict[str, ToolCall] = {}
    for message in messages:
        if message.role == "user" and not message.harness_note:
            calls.clear()
        if message.role == "assistant":
            calls.update((call.id, call) for call in message.tool_calls)
        if message.harness_note:
            continue
        if message.role == "tool":
            rows.append(_tool_row(message, calls.get(message.tool_call_id or "")))
        elif message.role in {"user", "assistant"} and message.content.strip():
            row: dict[str, object] = {
                "rol": "kullanici" if message.role == "user" else "asistan",
                "metin": redact(message.content),
            }
            if message.tool_calls:
                row["ara"] = True
            if message.message_id:
                row["id"] = message.message_id
            rows.append(row)
    return rows

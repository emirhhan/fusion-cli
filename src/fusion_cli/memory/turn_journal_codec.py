"""Tur mesajı kodlaması: eski snapshot uyumu ve katı özgün segment ayrıştırması."""

from __future__ import annotations

import json

from ..core.original_trace import ORIGINAL_TRACE_ROLES
from ..core.redaction import redact, redact_value
from ..core.types import Message, ToolCall


def message_to(message: Message) -> dict[str, object]:
    return {
        "rol": message.role,
        "icerik": redact(message.content),
        "araclar": [
            {
                "id": redact(call.id),
                "ad": redact(call.name),
                "arguman": _redact_arguments(call.arguments),
            }
            for call in message.tool_calls
        ],
        "arac_id": redact(message.tool_call_id) if message.tool_call_id is not None else None,
        "ad": redact(message.name) if message.name is not None else None,
        "ok": message.ok,
        "tool_diff": redact(message.tool_diff) if message.tool_diff is not None else None,
        "harness": message.harness_note,
    }


def _redact_arguments(raw: str) -> str:
    """Araç argümanındaki sırları JSON'u BOZMADAN maskele.

    Düz `redact`, `{"api_key": "sk-…"}` biçimini `{[gizlendi], …}` yapıyordu
    (geçersiz JSON). JSON ise yapı korunur, yalnız sır taşıyan değer değişir.
    """
    try:
        data = json.loads(raw)
    except ValueError:
        return redact(raw)
    return json.dumps(redact_value(data), ensure_ascii=False)


def message_from(item: object) -> Message | None:
    if not isinstance(item, dict):
        return None
    role, content = item.get("rol"), item.get("icerik")
    if not isinstance(role, str) or not isinstance(content, str):
        return None
    raw_calls = item.get("araclar", [])
    if not isinstance(raw_calls, list):
        return None
    calls = tuple(
        ToolCall(
            id=str(call.get("id", "")),
            name=str(call.get("ad", "")),
            arguments=str(call.get("arguman", "")),
        )
        for call in raw_calls
        if isinstance(call, dict)
    )
    tool_call_id = item.get("arac_id")
    name = item.get("ad")
    ok = item.get("ok")
    return Message(
        role,
        content,
        tool_calls=calls,
        tool_call_id=tool_call_id if isinstance(tool_call_id, str) else None,
        name=name if isinstance(name, str) else None,
        ok=ok if isinstance(ok, bool) else None,
        tool_diff=item["tool_diff"] if isinstance(item.get("tool_diff"), str) else None,
        harness_note=bool(item.get("harness", False)),
    )


_ORIGINAL_MESSAGE_FIELDS = frozenset(
    {"rol", "icerik", "araclar", "arac_id", "ad", "ok", "tool_diff", "harness"}
)
_ORIGINAL_CALL_FIELDS = frozenset({"id", "ad", "arguman"})


def original_messages_from(items: object) -> tuple[Message, ...] | None:
    """Özgün kayıtta hiçbir öğeyi süzme, alanı uydurma veya türü dönüştürme."""
    if not isinstance(items, list) or not items:
        return None
    messages: list[Message] = []
    for item in items:
        message = _original_message_from(item)
        if message is None:
            return None
        messages.append(message)
    return tuple(messages)


def _original_message_from(item: object) -> Message | None:
    if not isinstance(item, dict) or set(item) != _ORIGINAL_MESSAGE_FIELDS:
        return None
    role, content, raw_calls = item["rol"], item["icerik"], item["araclar"]
    if (
        not isinstance(role, str)
        or role not in ORIGINAL_TRACE_ROLES
        or not isinstance(content, str)
        or not isinstance(raw_calls, list)
        or item["harness"] is not False
    ):
        return None
    tool_call_id, name, tool_diff, ok = item["arac_id"], item["ad"], item["tool_diff"], item["ok"]
    if (
        not _is_optional_string(tool_call_id)
        or not _is_optional_string(name)
        or not _is_optional_string(tool_diff)
        or (ok is not None and not isinstance(ok, bool))
    ):
        return None
    calls: list[ToolCall] = []
    for raw_call in raw_calls:
        call = _original_call_from(raw_call)
        if call is None:
            return None
        calls.append(call)
    return Message(
        role,
        content,
        tool_calls=tuple(calls),
        tool_call_id=tool_call_id,
        name=name,
        ok=ok,
        tool_diff=tool_diff,
        harness_note=False,
    )


def _is_optional_string(value: object) -> bool:
    return value is None or isinstance(value, str)


def _original_call_from(item: object) -> ToolCall | None:
    if not isinstance(item, dict) or set(item) != _ORIGINAL_CALL_FIELDS:
        return None
    identity, name, arguments = item["id"], item["ad"], item["arguman"]
    if (
        not isinstance(identity, str)
        or not identity
        or not isinstance(name, str)
        or not name
        or not isinstance(arguments, str)
    ):
        return None
    return ToolCall(identity, name, arguments)

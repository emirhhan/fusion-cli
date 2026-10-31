"""Anthropic Messages API (`/v1/messages`) ↔ Fusion `CompletionRequest`/`ModelResult` (P-074).

Claude SDK'ları ve Claude Code (`ANTHROPIC_BASE_URL`) Fusion'ı sağlayıcı olarak kullanabilsin
diye şema çevirisi. Araçlar: Anthropic `tools[].input_schema` → OpenAI `function`
şeması; `tool_use` blokları → `ToolCall`; `tool_result` blokları → `role=tool` mesajı.
Akış olayları Anthropic SSE sözleşmesidir (`event:` satırlı): message_start,
content_block_start/delta/stop, message_delta, message_stop.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from typing import Any

from ..config.models import RuntimeConfig
from ..core.types import CompletionRequest, Message, ModelResult, ToolCall
from .translate import GatewayError, _number, split_content

#: Anthropic `stop_reason` değerleri.
_STOP_END = "end_turn"
_STOP_TOOL = "tool_use"
_STOP_MAX = "max_tokens"


def to_request(
    payload: Mapping[str, object], runtime: RuntimeConfig
) -> tuple[CompletionRequest, str, bool]:
    """Anthropic isteğini `(CompletionRequest, model, stream)` üçlüsüne çevir."""
    model = str(payload.get("model", "")).strip()
    if not model:
        raise GatewayError("'model' alanı zorunludur (profil adı ya da model kimliği).")
    stream = bool(payload.get("stream", False))
    messages = [*_system_messages(payload.get("system")), *_messages(payload.get("messages"))]
    temperature = _number(payload.get("temperature"))
    max_tokens = payload.get("max_tokens")
    request = CompletionRequest(
        messages=tuple(messages),
        temperature=temperature if temperature is not None else runtime.temperature,
        max_tokens=int(max_tokens)
        if isinstance(max_tokens, int) and not isinstance(max_tokens, bool)
        else runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
        tools=_tools(payload.get("tools")),
    )
    return request, model, stream


def _system_messages(raw: object) -> list[Message]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [Message(role="system", content=raw)] if raw.strip() else []
    if isinstance(raw, list):
        text = "\n".join(
            str(block.get("text", ""))
            for block in raw
            if isinstance(block, Mapping) and block.get("type") == "text"
        )
        return [Message(role="system", content=text)] if text.strip() else []
    raise GatewayError("'system' metin ya da metin blokları listesi olmalı.")


def _messages(raw: object) -> list[Message]:
    if not isinstance(raw, list) or not raw:
        raise GatewayError("'messages' alanı zorunludur ve boş olamaz.")
    result: list[Message] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise GatewayError("her mesaj bir nesne olmalı.")
        role = str(item.get("role", "user"))
        content = item.get("content")
        if isinstance(content, str) or content is None:
            result.append(Message(role=role, content=content or ""))
            continue
        if not isinstance(content, list):
            raise GatewayError("mesaj içeriği metin ya da blok listesi olmalı.")
        result.extend(_blocks_to_messages(role, content))
    return result


def _blocks_to_messages(role: str, blocks: Sequence[object]) -> list[Message]:
    """Blok listesini Fusion mesajlarına aç: metin+görsel tek mesaj, tool_use/tool_result ayrı."""
    parts: list[dict[str, Any]] = []
    tool_calls: list[ToolCall] = []
    tool_results: list[Message] = []
    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append({"type": "text", "text": str(block.get("text", ""))})
        elif kind == "image":
            source = block.get("source")
            if isinstance(source, Mapping) and source.get("type") == "base64":
                uri = (
                    f"data:{source.get('media_type', 'image/png')};base64,{source.get('data', '')}"
                )
                parts.append({"type": "image_url", "image_url": {"url": uri}})
            elif isinstance(source, Mapping) and source.get("type") == "url":
                parts.append(
                    {"type": "image_url", "image_url": {"url": str(source.get("url", ""))}}
                )
        elif kind == "tool_use":
            tool_calls.append(
                ToolCall(
                    id=str(block.get("id", "")),
                    name=str(block.get("name", "")),
                    arguments=json.dumps(block.get("input", {}), ensure_ascii=False),
                )
            )
        elif kind == "tool_result":
            inner = block.get("content")
            text = inner if isinstance(inner, str) else _text_of_blocks(inner)
            tool_results.append(
                Message(role="tool", content=text, tool_call_id=str(block.get("tool_use_id", "")))
            )
    # Önce araç sonuçları, sonra metin/görsel: Claude Code bir turda `tool_result` bloklarıyla
    # birlikte `text` (system-reminder) gönderir; OpenAI uyumlu sağlayıcılar `tool_calls`
    # taşıyan assistant mesajından HEMEN sonra `tool` mesajı bekler, araya giren user
    # mesajında 400 döner. Ölçüldü (31 Ekim): eski sıra ikinci turdan itibaren döngüyü kırıyordu.
    messages: list[Message] = list(tool_results)
    if parts or tool_calls:
        text, images = split_content(parts) if parts else ("", ())
        messages.append(
            Message(role=role, content=text, images=images, tool_calls=tuple(tool_calls))
        )
    return messages


def _text_of_blocks(raw: object) -> str:
    if not isinstance(raw, list):
        return ""
    return "\n".join(
        str(block.get("text", ""))
        for block in raw
        if isinstance(block, Mapping) and block.get("type") == "text"
    )


def _tools(raw: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(raw, list):
        return ()
    tools: list[Mapping[str, object]] = []
    for tool in raw:
        if not isinstance(tool, Mapping) or not tool.get("name"):
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": str(tool["name"]),
                    "description": str(tool.get("description", "")),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
        )
    return tuple(tools)


# --------------------------------------------------------------------------- #
# Cevap
# --------------------------------------------------------------------------- #


def _stop_reason(result: ModelResult) -> str:
    if result.tool_calls:
        return _STOP_TOOL
    if result.truncated:
        return _STOP_MAX
    return _STOP_END


def _content_blocks(result: ModelResult) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if result.text:
        blocks.append({"type": "text", "text": result.text})
    for call in result.tool_calls:
        try:
            arguments = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            arguments = {"_raw": call.arguments}
        blocks.append({"type": "tool_use", "id": call.id, "name": call.name, "input": arguments})
    return blocks


def _usage(result: ModelResult) -> dict[str, int]:
    return {
        "input_tokens": result.usage.prompt_tokens,
        "output_tokens": result.usage.completion_tokens,
    }


def message_id() -> str:
    return f"msg_fusion_{int(time.time() * 1000)}"


def to_message(result: ModelResult, model: str, *, msg_id: str | None = None) -> dict[str, Any]:
    """Fusion sonucunu Anthropic `message` nesnesine çevir."""
    return {
        "id": msg_id or message_id(),
        "type": "message",
        "role": "assistant",
        "model": result.model or model,
        "content": _content_blocks(result),
        "stop_reason": _stop_reason(result),
        "stop_sequence": None,
        "usage": _usage(result),
    }


def count_tokens(payload: Mapping[str, object], runtime: RuntimeConfig) -> dict[str, int]:
    """`/v1/messages/count_tokens` (Claude Code çağırır): sağlayıcıdan bağımsız kaba tahmin.

    Fusion'da modele özel bir belirteçleyici yok; ~4 karakter = 1 token varsayımı
    (`observability` ile aynı kaba ölçü). Araç şemaları da sayılır.
    """
    request, _model, _stream = to_request(payload, runtime)
    chars = sum(len(message.content or "") for message in request.messages)
    chars += sum(len(json.dumps(tool, ensure_ascii=False)) for tool in request.tools)
    return {"input_tokens": max(1, chars // 4)}


def error_body(message: str, *, kind: str = "invalid_request_error") -> dict[str, Any]:
    """Anthropic hata zarfı."""
    return {"type": "error", "error": {"type": kind, "message": message}}


# --- akış olayları ---------------------------------------------------------- #


def event_message_start(model: str, *, msg_id: str) -> tuple[str, dict[str, Any]]:
    return (
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )


def event_block_start(index: int, block: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    return (
        "content_block_start",
        {"type": "content_block_start", "index": index, "content_block": block},
    )


def event_text_delta(index: int, text: str) -> tuple[str, dict[str, Any]]:
    return (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "text_delta", "text": text},
        },
    )


def event_json_delta(index: int, partial_json: str) -> tuple[str, dict[str, Any]]:
    return (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "input_json_delta", "partial_json": partial_json},
        },
    )


def event_block_stop(index: int) -> tuple[str, dict[str, Any]]:
    return ("content_block_stop", {"type": "content_block_stop", "index": index})


def event_message_delta(result: ModelResult) -> tuple[str, dict[str, Any]]:
    return (
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": _stop_reason(result), "stop_sequence": None},
            "usage": {"output_tokens": result.usage.completion_tokens},
        },
    )


def event_message_stop() -> tuple[str, dict[str, Any]]:
    return ("message_stop", {"type": "message_stop"})


def event_error(message: str) -> tuple[str, dict[str, Any]]:
    return ("error", error_body(message, kind="api_error"))

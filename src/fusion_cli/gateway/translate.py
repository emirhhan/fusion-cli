"""OpenAI ↔ Fusion çevirisi — yerel gateway'in konuştuğu dil.

Gateway, OpenAI'nin `/v1/chat/completions` biçimini kabul eder (böylece HER araç
Fusion'a bağlanabilir) ve içeride Fusion'ın canonical `CompletionRequest`/`ModelResult`
tiplerine çevirir. Çeviri saf ve test edilebilirdir: ağ ya da sunucu gerektirmez.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from ..config.models import RuntimeConfig
from ..core.types import CompletionRequest, Message, ModelResult, ToolCall


class GatewayError(Exception):
    """İstek biçimi hatalı — gateway 400 döndürür (sunucuyu çökertmez)."""


def _content_to_text(content: object) -> str:
    """OpenAI içerik alanı metin ya da parça listesi olabilir; metne indir."""
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        parts = []
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "".join(parts)
    return ""


def parse_messages(payload: Mapping[str, object]) -> tuple[Message, ...]:
    """OpenAI `messages` dizisini Fusion `Message` demetine çevir."""
    raw = payload.get("messages")
    if not isinstance(raw, list) or not raw:
        raise GatewayError("'messages' alanı zorunludur ve boş olamaz.")
    messages: list[Message] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise GatewayError("her mesaj bir nesne olmalı.")
        role = str(item.get("role", "user"))
        messages.append(Message(role=role, content=_content_to_text(item.get("content", ""))))
    return tuple(messages)


def to_request(
    payload: Mapping[str, object], runtime: RuntimeConfig
) -> tuple[CompletionRequest, str, bool]:
    """OpenAI isteğini `(CompletionRequest, model_adı, stream)` üçlüsüne çevir.

    Eksik alanlar için `runtime` varsayılanları kullanılır — koda gömülü değer yok.
    """
    model = str(payload.get("model", "")).strip()
    if not model:
        raise GatewayError("'model' alanı zorunludur (profil adı ya da model kimliği).")
    stream = bool(payload.get("stream", False))
    temperature = payload.get("temperature")
    max_tokens = payload.get("max_tokens")
    tools_raw = payload.get("tools")
    tools = tuple(tools_raw) if isinstance(tools_raw, list) else ()
    effort = payload.get("reasoning_effort")
    request = CompletionRequest(
        messages=parse_messages(payload),
        temperature=float(temperature)
        if isinstance(temperature, (int, float))
        else runtime.temperature,
        max_tokens=int(max_tokens) if isinstance(max_tokens, int) else runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
        tools=tools,
        reasoning_effort=str(effort) if isinstance(effort, str) else None,
    )
    return request, model, stream


def _tool_calls_json(tool_calls: tuple[ToolCall, ...]) -> list[dict[str, Any]]:
    return [
        {
            "id": call.id,
            "type": "function",
            "function": {"name": call.name, "arguments": call.arguments},
        }
        for call in tool_calls
    ]


def _finish_reason(result: ModelResult) -> str:
    if result.tool_calls:
        return "tool_calls"
    if result.truncated:
        return "length"
    return "stop"


def to_openai_response(result: ModelResult, model: str) -> dict[str, Any]:
    """Fusion sonucunu OpenAI `chat.completion` nesnesine çevir."""
    message: dict[str, Any] = {"role": "assistant", "content": result.text or None}
    if result.tool_calls:
        message["tool_calls"] = _tool_calls_json(result.tool_calls)
    return {
        "id": f"fusion-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        # Gerçekten cevap veren model; router başka bir modele düşmüş olabilir.
        "model": result.model or model,
        "choices": [{"index": 0, "message": message, "finish_reason": _finish_reason(result)}],
        "usage": {
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "total_tokens": result.usage.prompt_tokens + result.usage.completion_tokens,
        },
    }


def to_openai_chunk(delta: str, model: str, *, chunk_id: str) -> dict[str, Any]:
    """Akış sırasında bir metin parçasını OpenAI `chat.completion.chunk`'a çevir."""
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
    }


def final_chunk(model: str, *, chunk_id: str, finish_reason: str = "stop") -> dict[str, Any]:
    """Akışı kapatan son parça (delta boş, finish_reason dolu)."""
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
    }

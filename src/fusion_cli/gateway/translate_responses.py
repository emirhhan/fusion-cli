"""OpenAI Responses API (`/v1/responses`) ↔ Fusion `CompletionRequest`/`ModelResult` (P-074).

Codex CLI ve yeni OpenAI SDK'ları chat.completions yerine bunu konuşur. İstek `input`
(metin ya da öğe listesi) + `instructions`; cevap `output[]` öğeleri (`message` →
`output_text`, `function_call`). Akış olayları `response.*` adlarıyla `event:` satırlı SSE.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any

from ..config.models import RuntimeConfig
from ..core.types import CompletionRequest, Message, ModelResult, ToolCall
from .translate import GatewayError, _number, split_content


def to_request(
    payload: Mapping[str, object], runtime: RuntimeConfig
) -> tuple[CompletionRequest, str, bool]:
    """Responses isteğini `(CompletionRequest, model, stream)` üçlüsüne çevir."""
    model = str(payload.get("model", "")).strip()
    if not model:
        raise GatewayError("'model' alanı zorunludur (profil adı ya da model kimliği).")
    stream = bool(payload.get("stream", False))
    messages: list[Message] = []
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append(Message(role="system", content=instructions))
    messages.extend(_input_messages(payload.get("input")))
    if not any(message.role != "system" for message in messages):
        raise GatewayError("'input' alanı zorunludur ve boş olamaz.")
    temperature = _number(payload.get("temperature"))
    max_tokens = payload.get("max_output_tokens")
    effort = None
    reasoning = payload.get("reasoning")
    if isinstance(reasoning, Mapping) and isinstance(reasoning.get("effort"), str):
        effort = str(reasoning["effort"])
    request = CompletionRequest(
        messages=tuple(messages),
        temperature=temperature if temperature is not None else runtime.temperature,
        max_tokens=int(max_tokens)
        if isinstance(max_tokens, int) and not isinstance(max_tokens, bool)
        else runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
        tools=_tools(payload.get("tools")),
        reasoning_effort=effort,
    )
    return request, model, stream


def _input_messages(raw: object) -> list[Message]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [Message(role="user", content=raw)]
    if not isinstance(raw, list):
        raise GatewayError("'input' metin ya da öğe listesi olmalı.")
    messages: list[Message] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise GatewayError("her input öğesi bir nesne olmalı.")
        kind = item.get("type", "message")
        if kind == "message" or "role" in item:
            text, images = split_content(_as_openai_parts(item.get("content")))
            messages.append(
                Message(role=str(item.get("role", "user")), content=text, images=images)
            )
        elif kind == "function_call":
            messages.append(
                Message(
                    role="assistant",
                    content="",
                    tool_calls=(
                        ToolCall(
                            id=str(item.get("call_id") or item.get("id", "")),
                            name=str(item.get("name", "")),
                            arguments=str(item.get("arguments", "{}")),
                        ),
                    ),
                )
            )
        elif kind == "function_call_output":
            output = item.get("output", "")
            messages.append(
                Message(
                    role="tool",
                    content=output if isinstance(output, str) else json.dumps(output),
                    tool_call_id=str(item.get("call_id", "")),
                )
            )
    return messages


def _as_openai_parts(content: object) -> object:
    """Responses içerik parçalarını (`input_text`, `input_image`) OpenAI chat parçalarına çevir."""
    if not isinstance(content, list):
        return content or ""
    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, Mapping):
            continue
        kind = part.get("type")
        if kind in ("input_text", "output_text", "text"):
            parts.append({"type": "text", "text": str(part.get("text", ""))})
        elif kind == "input_image":
            url = part.get("image_url")
            if isinstance(url, Mapping):
                url = url.get("url")
            parts.append({"type": "image_url", "image_url": {"url": str(url or "")}})
    return parts


def _tools(raw: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(raw, list):
        return ()
    tools: list[Mapping[str, object]] = []
    for tool in raw:
        if not isinstance(tool, Mapping) or tool.get("type") != "function":
            continue
        # Responses biçimi düz (`name` üstte); eski iç içe `function` biçimi de kabul.
        inner = tool.get("function") if isinstance(tool.get("function"), Mapping) else tool
        if not isinstance(inner, Mapping) or not inner.get("name"):
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": str(inner["name"]),
                    "description": str(inner.get("description", "")),
                    "parameters": inner.get("parameters", {"type": "object", "properties": {}}),
                },
            }
        )
    return tuple(tools)


# --------------------------------------------------------------------------- #
# Cevap
# --------------------------------------------------------------------------- #


def response_id() -> str:
    return f"resp_fusion_{int(time.time() * 1000)}"


def message_item(result: ModelResult, *, item_id: str) -> dict[str, Any]:
    return {
        "type": "message",
        "id": item_id,
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": result.text or "", "annotations": []}],
    }


def function_call_items(result: ModelResult) -> list[dict[str, Any]]:
    return [
        {
            "type": "function_call",
            "id": f"fc_{call.id}",
            "call_id": call.id,
            "name": call.name,
            "arguments": call.arguments or "{}",
            "status": "completed",
        }
        for call in result.tool_calls
    ]


def to_response(result: ModelResult, model: str, *, resp_id: str | None = None) -> dict[str, Any]:
    """Fusion sonucunu Responses `response` nesnesine çevir."""
    resp_id = resp_id or response_id()
    output: list[dict[str, Any]] = []
    if result.text or not result.tool_calls:
        output.append(message_item(result, item_id=f"msg_{resp_id}"))
    output.extend(function_call_items(result))
    usage = result.usage
    return {
        "id": resp_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed" if result.is_usable else "failed",
        "error": None if result.is_usable else {"code": "provider_error", "message": result.error},
        "model": result.model or model,
        "output": output,
        "output_text": result.text or "",
        "usage": {
            "input_tokens": usage.prompt_tokens,
            "output_tokens": usage.completion_tokens,
            "total_tokens": usage.prompt_tokens + usage.completion_tokens,
        },
    }


def event(name: str, **fields: object) -> tuple[str, dict[str, Any]]:
    """`event: <ad>` satırı ve `type` alanı aynı adı taşır (Responses SSE sözleşmesi)."""
    return name, {"type": name, **fields}

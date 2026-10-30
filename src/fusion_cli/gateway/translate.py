"""OpenAI ↔ Fusion çevirisi — yerel gateway'in konuştuğu dil.

Gateway, OpenAI'nin `/v1/chat/completions` biçimini kabul eder (böylece HER araç
Fusion'a bağlanabilir) ve içeride Fusion'ın canonical `CompletionRequest`/`ModelResult`
tiplerine çevirir. Çeviri saf ve test edilebilirdir: ağ ya da sunucu gerektirmez.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from typing import Any

from ..config.models import RuntimeConfig
from ..core.types import CompletionRequest, Message, ModelResult, ToolCall


class GatewayError(Exception):
    """İstek biçimi hatalı — gateway 400 döndürür (sunucuyu çökertmez)."""


def _content_to_text(content: object) -> str:
    """OpenAI içerik alanı metin ya da parça listesi olabilir; metne indir."""
    return _split_content(content)[0]


def _split_content(content: object) -> tuple[str, tuple[str, ...]]:
    """İçeriği `(metin, görseller)` olarak ayır.

    `image_url` parçası eskiden SESSİZCE atılıyordu: görsel gönderen istemci cevabı
    görselsiz alıyor ve hata görmüyordu (E1-14). Artık `data:` URI'ler `Message.images`
    ile iletilir; uzak adresler (indirmeyiz) ve tanınmayan parça tipleri AÇIK hatadır.
    """
    if isinstance(content, str):
        return content, ()
    if not isinstance(content, Sequence):
        return "", ()
    parts: list[str] = []
    images: list[str] = []
    for part in content:
        if not isinstance(part, Mapping):
            continue
        kind = part.get("type")
        if kind == "text":
            parts.append(str(part.get("text", "")))
        elif kind == "image_url":
            images.append(_image_data_uri(part.get("image_url")))
        elif kind is not None:
            raise GatewayError(f"desteklenmeyen içerik türü: {kind!r} (yalnız text ve image_url).")
    return "".join(parts), tuple(images)


def _image_data_uri(raw: object) -> str:
    url = raw.get("url") if isinstance(raw, Mapping) else raw
    if isinstance(url, str) and url.startswith("data:image/"):
        return url
    raise GatewayError(
        "image_url yalnız 'data:image/...' (base64) olabilir; uzak adresler indirilmez."
    )


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
        tool_call_id = item.get("tool_call_id")
        name = item.get("name")
        text, images = _split_content(item.get("content") or "")
        messages.append(
            Message(
                role=role,
                content=text,
                images=images,
                tool_calls=_parse_tool_calls(item.get("tool_calls")),
                tool_call_id=str(tool_call_id) if tool_call_id else None,
                name=str(name) if name else None,
            )
        )
    return tuple(messages)


def _parse_tool_calls(raw: object) -> tuple[ToolCall, ...]:
    """Asistan mesajındaki OpenAI `tool_calls` dizisi. Düşürülürse sonraki `tool` mesajı
    sahipsiz kalır ve sağlayıcı isteği reddeder (ölçüldü, 9 Ekim 2026: Kits + NIM)."""
    if not isinstance(raw, list):
        return ()
    calls: list[ToolCall] = []
    for call in raw:
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(call, Mapping) or not isinstance(function, Mapping):
            raise GatewayError("her araç çağrısında 'id' ve 'function' olmalı.")
        call_id, name = call.get("id"), function.get("name")
        if not call_id or not name:
            raise GatewayError("her araç çağrısında 'id' ve 'function.name' olmalı.")
        arguments = function.get("arguments")
        calls.append(
            ToolCall(
                id=str(call_id),
                name=str(name),
                arguments=_arguments_text(arguments),
            )
        )
    return tuple(calls)


def _arguments_text(arguments: object) -> str:
    """Araç argümanları HAM JSON metnidir; zayıf istemciler nesne gönderebilir.

    Nesne eskiden `"{}"`a düşüyor ve argümanlar sessizce kayboluyordu (E1-14).
    """
    if isinstance(arguments, str):
        return arguments
    if isinstance(arguments, Mapping):
        return json.dumps(arguments, ensure_ascii=False)
    return "{}"


def _number(value: object) -> bool:
    """Sayı mı? `bool` int'in alt sınıfıdır: `max_tokens: true` 1 token olmasın (E1-14)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
    # Yeni OpenAI alanı `max_completion_tokens` öncelikli; eski `max_tokens` yedek.
    max_tokens = payload.get("max_completion_tokens", payload.get("max_tokens"))
    tools_raw = payload.get("tools")
    tools = tuple(tools_raw) if isinstance(tools_raw, list) else ()
    effort = payload.get("reasoning_effort")
    request = CompletionRequest(
        messages=parse_messages(payload),
        temperature=float(temperature) if _number(temperature) else runtime.temperature,
        max_tokens=int(max_tokens)
        if isinstance(max_tokens, int) and not isinstance(max_tokens, bool)
        else runtime.max_tokens,
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


def tool_calls_chunk(
    tool_calls: tuple[ToolCall, ...], model: str, *, chunk_id: str
) -> dict[str, Any]:
    """Akışta modelin araç çağrılarını tek parçada gönder (OpenAI `delta.tool_calls`)."""
    calls = [{"index": index, **call} for index, call in enumerate(_tool_calls_json(tool_calls))]
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"tool_calls": calls}, "finish_reason": None}],
    }


def stream_error(result: ModelResult) -> dict[str, Any]:
    """Akış ortasında model hatası: OpenAI istemcileri `error` olayını hata olarak fırlatır."""
    message = result.error or "model kullanılabilir bir cevap üretmedi"
    return {"error": {"message": message, "type": "provider_error"}}


def final_chunk(model: str, *, chunk_id: str, finish_reason: str = "stop") -> dict[str, Any]:
    """Akışı kapatan son parça (delta boş, finish_reason dolu)."""
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
    }

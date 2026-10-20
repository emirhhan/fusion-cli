"""Sağlayıcı model katalogları.

Varsayılan modeller sağlayıcı tarafında SESSİZCE kaybolabiliyor: taşıma sırasında
`z-ai/glm-5.2` NIM kataloğunda hiç yoktu ve `tencent/hy3:free` ücretsiz katmandan
çıkarılmıştı — ikisi de yapılandırmada duruyordu ve hiçbir model yanıt vermiyordu.

Bu modül canlı katalogdan gerçekten kullanılabilir modelleri listeler; bir daha
"neden hiçbir şey çalışmıyor?" sorusunu tahminle cevaplamak gerekmez.

Ağ ya da ayrıştırma hatasında istisna fırlatmaz; boş liste döner.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx

from ..core.constants import WEB_TIMEOUT_S
from ..core.types import ToolCall

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
NIM_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"

#: OpenRouter'da ücretsiz sayılan girdi fiyatları.
_FREE_PRICES = frozenset({"0", "0.0", "0.00"})


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """Katalogdan gelen bir model."""

    #: LiteLLM biçiminde kullanılabilir kimlik ("<sağlayıcı>/<model>").
    model_id: str
    provider: str
    context_length: int = 0
    #: Canlı katalog araç çağrısını açıkça bildiriyorsa; NIM bu bilgiyi vermez.
    supports_tools: bool | None = None


@dataclass(frozen=True, slots=True)
class CatalogLoadResult:
    """Boş katalog ile erişim hatasını ayıran tek katalog sonucu."""

    entries: tuple[CatalogEntry, ...] = ()
    error: str | None = None


def load_openrouter_free(timeout_s: float = WEB_TIMEOUT_S) -> CatalogLoadResult:
    return _load_openrouter(True, timeout_s)


def load_openrouter_paid(timeout_s: float = WEB_TIMEOUT_S) -> CatalogLoadResult:
    return _load_openrouter(False, timeout_s)


def _load_openrouter(is_free: bool, timeout_s: float) -> CatalogLoadResult:
    data, error = _load_json(OPENROUTER_MODELS_URL, timeout_s=timeout_s)
    entries = tuple(
        sorted(
            (
                CatalogEntry(
                    model_id=f"openrouter/{item['id']}",
                    provider="openrouter",
                    context_length=_as_int(item.get("context_length")),
                    supports_tools=_supports_tools(item),
                )
                for item in data
                if item.get("id") and _is_free(item) is is_free
            ),
            key=lambda entry: entry.model_id,
        )
    )
    return CatalogLoadResult(entries, error)


def load_nim(timeout_s: float = WEB_TIMEOUT_S) -> CatalogLoadResult:
    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        return CatalogLoadResult()
    data, error = _load_json(
        NIM_MODELS_URL, timeout_s=timeout_s, headers={"Authorization": f"Bearer {api_key}"}
    )
    entries = tuple(
        sorted(
            (
                CatalogEntry(model_id=f"nvidia_nim/{item['id']}", provider="nvidia_nim")
                for item in data
                if item.get("id")
            ),
            key=lambda entry: entry.model_id,
        )
    )
    return CatalogLoadResult(entries, error)


def fetch_openrouter_free(timeout_s: float = WEB_TIMEOUT_S) -> tuple[CatalogEntry, ...]:
    """Eski tuple arayüzü aynı typed kaynaktan üretilir."""
    return load_openrouter_free(timeout_s).entries


def fetch_openrouter_paid(timeout_s: float = WEB_TIMEOUT_S) -> tuple[CatalogEntry, ...]:
    return load_openrouter_paid(timeout_s).entries


def fetch_nim(timeout_s: float = WEB_TIMEOUT_S) -> tuple[CatalogEntry, ...]:
    return load_nim(timeout_s).entries


TOOL_CAPABILITY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "sum",
        "description": "Add two integers",
        "parameters": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    },
}
# Mevcut NIM sondasının çıktı bütçesi; doktor aynı küçük araç sözleşmesini kullanır.
TOOL_PROBE_MAX_TOKENS = 80


def probe_nim_tools(model_id: str, timeout_s: float = 90.0) -> tuple[bool, str]:
    """Bir NIM modelinin gerçekten sohbet ve araç çağrısı yapabildiğini ölç.

    ``/models`` kaydı tek başına yeterli değil: aynı listede kapalı 404 uçları,
    embedding modelleri ve araç kullanmayan modeller de bulunuyor.
    """
    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key or not model_id.startswith("nvidia_nim/"):
        return False, "NIM anahtarı veya model kimliği geçersiz."
    payload = {
        "model": model_id.removeprefix("nvidia_nim/"),
        "messages": [{"role": "user", "content": "Use the sum tool to add 2 and 3."}],
        "max_tokens": TOOL_PROBE_MAX_TOKENS,
        "tools": [TOOL_CAPABILITY_SCHEMA],
        "tool_choice": "auto",
    }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        return False, f"NIM doğrulaması başarısız ({status or type(error).__name__})."
    choices = result.get("choices") if isinstance(result, dict) else None
    message = (
        choices[0].get("message")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict)
        else None
    )
    calls = message.get("tool_calls") if isinstance(message, dict) else None
    if not isinstance(calls, list) or not any(_valid_sum_call(call) for call in calls):
        return False, "Model geçerli bir araç çağrısı üretmedi."
    return True, ""


def valid_capability_call(call: ToolCall) -> bool:
    """SDK'nin gerçek çağrısı aynı native sonda şemasına uymalı."""
    return _valid_sum_call({"function": {"name": call.name, "arguments": call.arguments}})


def _valid_sum_call(call: object) -> bool:
    if not isinstance(call, dict):
        return False
    function = call.get("function")
    if not isinstance(function, dict) or function.get("name") != "sum":
        return False
    try:
        arguments = json.loads(function.get("arguments", ""))
    except (TypeError, ValueError):
        return False
    return isinstance(arguments, dict) and arguments.get("a") == 2 and arguments.get("b") == 3


def _as_int(value: object) -> int:
    """Katalog alanları tipsizdir; sayıya çevrilemeyen değer 0 sayılır."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _supports_tools(item: dict[str, object]) -> bool | None:
    parameters = item.get("supported_parameters")
    return "tools" in parameters if isinstance(parameters, list) else None


def _is_free(item: dict[str, object]) -> bool:
    pricing = item.get("pricing")
    if not isinstance(pricing, dict):
        return False
    return all(
        str(pricing.get(field, "")).strip() in _FREE_PRICES for field in ("prompt", "completion")
    )


def fetch_ollama(timeout_s: float = 0.75) -> tuple[CatalogEntry, ...]:
    """Discover optional local models without cloud keys or proxy credentials."""
    try:
        with httpx.Client(timeout=timeout_s, trust_env=False) as client:
            response = client.get("http://127.0.0.1:11434/api/tags")
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return ()
    models = payload.get("models", []) if isinstance(payload, dict) else []
    if not isinstance(models, list):
        return ()
    return tuple(
        CatalogEntry(f"ollama_chat/{row['name']}", "ollama")
        for row in models
        if isinstance(row, dict) and isinstance(row.get("name"), str) and row["name"].strip()
    )


def _load_json(
    url: str, *, timeout_s: float, headers: dict[str, str] | None = None
) -> tuple[list[dict[str, object]], str | None]:
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.get(url, headers=headers or {})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return [], "Model kataloğu okunamadı; yeniden dene."
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return [], "Model kataloğu geçerli bir liste döndürmedi; yeniden dene."
    return [item for item in data if isinstance(item, dict)], None

"""MCP araç şemasının ham (sunucunun yazdığı) biçimi — Anthropic modellerine (#262).

Claude Code MCP aracının `inputSchema`'sını olduğu gibi gönderir (code.claude.com/docs/en/mcp).
Fusion çok sağlayıcılıdır: `$ref`/`anyOf`/derin şema Gemini, Mistral ve bazı OpenRouter
modellerinde 400 verdiği için kayıt defterindeki şema sadeleştirilmiş kopyadır (bkz.
`mcp_bridge/schema.py`; döngünün argüman doğrulaması da onu kullanır). Bu modül aynı aracın
ham şemasını saklar; JSON Schema'yı eksiksiz kabul eden sağlayıcı (Anthropic/Claude)
isteğinde sadeleştirilmiş şemanın yerine ham şema konur.

Eşleme ad + sadeleştirilmiş şemanın parmak iziyledir: başka kaynaktan aynı adla gelen bir
araç (ör. yenilenen tanım) yanlış ham şemayı almaz. Yalnız stdlib.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

__all__ = [
    "accepts_raw_schemas",
    "forget_raw_schema",
    "remember_raw_schema",
    "with_raw_schemas",
]

#: araç adı → (sadeleştirilmiş şemanın parmak izi, ham şema)
_RAW: dict[str, tuple[str, dict[str, object]]] = {}
_RAW_MODEL_MARKERS = ("anthropic/", "claude")


def _fingerprint(schema: Mapping[str, object]) -> str:
    return json.dumps(schema, sort_keys=True, ensure_ascii=False, default=str)


def remember_raw_schema(
    name: str, simplified: Mapping[str, object], raw: Mapping[str, object] | None
) -> None:
    """Aracın ham şemasını kaydet; üst düzeyi nesne olmayan ya da aynı şema kaydedilmez."""
    if not isinstance(raw, Mapping) or raw.get("type") != "object":
        _RAW.pop(name, None)
        return
    raw_copy = json.loads(json.dumps(raw, default=str))
    if raw_copy == dict(simplified):
        _RAW.pop(name, None)
        return
    _RAW[name] = (_fingerprint(simplified), raw_copy)


def forget_raw_schema(name: str) -> None:
    _RAW.pop(name, None)


def accepts_raw_schemas(model: str) -> bool:
    """Ham JSON Schema'yı eksiksiz kabul eden model mi (Anthropic/Claude)?"""
    lowered = model.lower()
    return any(marker in lowered for marker in _RAW_MODEL_MARKERS)


def with_raw_schemas(tools: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """OpenAI biçimli araç listesinde ham şeması bilinen MCP araçlarının şemasını değiştir."""
    result: list[dict[str, object]] = []
    for tool in tools:
        item = dict(tool)
        function = item.get("function")
        if isinstance(function, Mapping):
            entry = _RAW.get(str(function.get("name", "")))
            parameters = function.get("parameters")
            if (
                entry is not None
                and isinstance(parameters, Mapping)
                and _fingerprint(parameters) == entry[0]
            ):
                item["function"] = {**dict(function), "parameters": entry[1]}
        result.append(item)
    return result

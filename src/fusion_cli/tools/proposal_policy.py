"""Öneri şemasının desteklenen ortak alt kümesi."""

from __future__ import annotations

_SCHEMA_KEYS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minimum",
        "maximum",
        "minItems",
    }
)
_SCHEMA_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})


def is_supported_schema(schema: object) -> bool:
    """Değer doğrulayıcısının sessizce atladığı şema biçimlerini kabul etme."""
    if not isinstance(schema, dict) or set(schema) - _SCHEMA_KEYS:
        return False
    if not isinstance(schema.get("type"), str) or schema["type"] not in _SCHEMA_TYPES:
        return False
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        return False
    if any(not isinstance(name, str) or name not in properties for name in required):
        return False
    if any(not is_supported_schema(child) for child in properties.values()):
        return False
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        return False
    if "items" in schema and not is_supported_schema(schema["items"]):
        return False
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        return False
    for bound in ("minimum", "maximum", "minItems"):
        if bound not in schema:
            continue
        value = schema[bound]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if bound == "minItems" and (not isinstance(value, int) or value < 0):
            return False
    return True

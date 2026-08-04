"""Emulated tool helpers and dependency-free schema validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..core.tool_emulation import (
    CALL_CLOSE,
    CALL_OPEN,
    EmulatedParse,
    parse_tool_calls,
    render_tool_example,
    render_tool_instructions,
)

__all__ = [
    "CALL_CLOSE",
    "CALL_OPEN",
    "EmulatedParse",
    "parse_tool_calls",
    "render_tool_example",
    "render_tool_instructions",
    "validate_arguments",
]


def validate_arguments(
    function_schema: Mapping[str, object],
    arguments: Mapping[str, object],
) -> tuple[str, ...]:
    """Validate the JSON-Schema subset used by built-in Fusion tools."""
    raw = function_schema.get("parameters")
    if isinstance(raw, Mapping):
        parameters = raw
    elif function_schema.get("type") == "object":
        parameters = function_schema
    else:
        return ()
    return tuple(_validate(parameters, arguments, path="arguments"))


def _validate(schema: Mapping[str, object], value: object, *, path: str) -> list[str]:
    errors: list[str] = []
    kind = schema.get("type")

    if kind == "object":
        if not isinstance(value, Mapping):
            return [f"{path}: JSON nesnesi olmalı"]
        required = schema.get("required", ())
        if isinstance(required, Sequence) and not isinstance(required, (str, bytes)):
            for field in required:
                if isinstance(field, str) and field not in value:
                    errors.append(f"{path}.{field}: zorunlu alan eksik")
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            for field, field_value in value.items():
                field_schema = properties.get(field)
                if isinstance(field, str) and isinstance(field_schema, Mapping):
                    errors.extend(_validate(field_schema, field_value, path=f"{path}.{field}"))
        return errors

    if kind == "array":
        if not isinstance(value, list):
            return [f"{path}: dizi olmalı"]
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                errors.extend(_validate(item_schema, item, path=f"{path}[{index}]"))
    elif kind == "string" and not isinstance(value, str):
        errors.append(f"{path}: metin olmalı")
    elif kind == "boolean" and not isinstance(value, bool):
        errors.append(f"{path}: boolean olmalı")
    elif kind == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        errors.append(f"{path}: tam sayı olmalı")
    elif kind == "number" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        errors.append(f"{path}: sayı olmalı")

    enum = schema.get("enum")
    if (
        isinstance(enum, Sequence)
        and not isinstance(enum, (str, bytes))
        and value not in enum
    ):
        errors.append(f"{path}: izin verilen değerlerden biri olmalı: {list(enum)}")
    return errors

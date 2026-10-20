"""Taklit araç yardımcıları ve üçüncü-parti gerektirmeyen şema doğrulama.

Modelin ürettiği argümanlar araç ÇALIŞMADAN önce şemaya karşı doğrulanır: eksik
alanı çalıştırıp hata almak yerine modele ne yanlış olduğunu söylemek turu kurtarır.
`jsonschema` bilinçli olarak kullanılmaz — bu doğrulama `core`/`config` sınırında da
çağrılabilmelidir ve o katmanlar üçüncü partiye bağımlı olamaz.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from ..core.tool_emulation import (
    CALL_CLOSE,
    CALL_OPEN,
    EmulatedParse,
    parse_tool_calls,
    render_call,
    render_tool_example,
    render_tool_instructions,
)

__all__ = [
    "CALL_CLOSE",
    "CALL_OPEN",
    "EmulatedParse",
    "coerce_arguments",
    "parse_tool_calls",
    "render_call",
    "render_tool_example",
    "render_tool_instructions",
    "validate_arguments",
]


#: Şemadaki tipe karşılık gelen Python tipi. Yalnız yapısal tipler taşınır: bir
#: metin alanına gelen metni "çözmek" veri kaybıdır, düzeltme değil.
_STRUCTURED_TYPES: Mapping[str, type] = {"array": list, "object": dict}


def _parameters_of(function_schema: Mapping[str, object]) -> Mapping[str, object] | None:
    """Fonksiyon şemasından parametre nesnesini çıkar."""
    raw = function_schema.get("parameters")
    if isinstance(raw, Mapping):
        return raw
    if function_schema.get("type") == "object":
        return function_schema
    return None


def coerce_arguments(
    function_schema: Mapping[str, object],
    arguments: Mapping[str, object],
) -> dict[str, object]:
    """Şemanın dizi/nesne beklediği alanları, JSON METNİ olarak geldiyse çöz.

    Ölçüldü (Gemini web, Godot koşusu): model `todo_write` çağrısında `todos`
    alanını dizi yerine o dizinin JSON metni olarak gönderdi. İçerik kusursuzdu,
    yalnız bir kez fazla kodlanmıştı; çağrı reddedildi ve adım bütçesinden bir
    hak boşa gitti. Bu, tüm sağlayıcılarda görülen bir kodlama hatasıdır.

    Dönüşüm DARDIR ve yalnız kanıt varken yapılır: alan şemada `array` ya da
    `object` olmalı, gelen değer metin olmalı ve çözülen JSON tam olarak beklenen
    tipe denk gelmelidir. Aksi hâlde değer olduğu gibi bırakılır ve doğrulama
    hatası modele görünür kalır — sessiz bir tahmin, açık bir hatadan kötüdür.
    """
    parameters = _parameters_of(function_schema)
    if parameters is None:
        return dict(arguments)
    properties = parameters.get("properties")
    if not isinstance(properties, Mapping):
        return dict(arguments)
    coerced = dict(arguments)
    for field, value in arguments.items():
        if not isinstance(value, str):
            continue
        field_schema = properties.get(field)
        if not isinstance(field_schema, Mapping):
            continue
        expected = _STRUCTURED_TYPES.get(str(field_schema.get("type")))
        if expected is None:
            continue
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(decoded, expected):
            coerced[field] = decoded
    return coerced


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
    elif kind == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        errors.append(f"{path}: sayı olmalı")

    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes)) and value not in enum:
        errors.append(f"{path}: izin verilen değerlerden biri olmalı: {list(enum)}")
    return errors

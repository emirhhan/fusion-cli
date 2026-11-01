"""Taklit araç yardımcıları ve üçüncü-parti gerektirmeyen şema doğrulama.

Modelin ürettiği argümanlar araç ÇALIŞMADAN önce şemaya karşı doğrulanır: eksik
alanı çalıştırıp hata almak yerine modele ne yanlış olduğunu söylemek turu kurtarır.
`jsonschema` bilinçli olarak kullanılmaz — bu doğrulama `core`/`config` sınırında da
çağrılabilmelidir ve o katmanlar üçüncü partiye bağımlı olamaz.

Desteklenen JSON Şeması alt kümesi: `type` (tek tür veya tür listesi), `enum`,
`anyOf`, `oneOf`, `properties`, `required`, `additionalProperties: false`,
`items` (tek şema), `minimum`, `maximum` ve `minItems`. Nesne/dizi kısıtları
yalnız ilgili türdeki değerlere uygulanır; `oneOf` tam bir dal eşleşmesi ister.
Tam JSON Şeması uygulaması değildir: bilinmeyen türler ve desteklenmeyen anahtarlar
(`$ref`, `allOf`, `format`, `pattern`, şema değerli `additionalProperties` dahil)
uyumluluk için değerlendirilmez. Girdi şemasının geçerliliğini denetlemez.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence

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
    "MESSAGE_REQUIRED_MISSING",
    "EmulatedParse",
    "coerce_arguments",
    "parse_tool_calls",
    "render_call",
    "render_tool_example",
    "render_tool_instructions",
    "validate_arguments",
]


#: `validate_arguments` zorunlu alan eksikliği hatasının sonek metni (çağıranlar ayırt edebilsin).
MESSAGE_REQUIRED_MISSING = "zorunlu alan eksik"

#: Şemadaki tipe karşılık gelen Python tipi. Yalnız yapısal tipler taşınır: bir
#: metin alanına gelen metni "çözmek" veri kaybıdır, düzeltme değil.
_STRUCTURED_TYPES: Mapping[str, type] = {"array": list, "object": dict}


def _to_integer(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None


def _to_number(text: str) -> float | None:
    try:
        number = float(text.strip())
    except ValueError:
        return None
    return number if number == number and abs(number) != float("inf") else None


def _to_boolean(text: str) -> bool | None:
    return {"true": True, "false": False}.get(text.strip().lower())


#: Metinle gelen sayı/bool değerleri için DAR dönüşüm: çevrilemezse None (olduğu gibi kalır).
#: Ölçüldü (30 Ekim): `"5"->5`, `"true"->True` düzeltilmiyor, her araç kendi toleransını
#: yazıyordu (dosya araçlarında var, browser/desktop/image'da yoktu).
_SCALAR_COERCERS = {"integer": _to_integer, "number": _to_number, "boolean": _to_boolean}


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
        kind = str(field_schema.get("type"))
        if kind in _SCALAR_COERCERS:
            scalar = _SCALAR_COERCERS[kind](value)
            if scalar is not None:
                coerced[field] = scalar
            continue
        expected = _STRUCTURED_TYPES.get(kind)
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
    """Araç argümanlarını modülde belgelenen JSON Şeması alt kümesiyle doğrula."""
    raw = function_schema.get("parameters")
    if isinstance(raw, Mapping):
        parameters = raw
    elif function_schema.get("type") == "object":
        parameters = function_schema
    else:
        return ()
    return tuple(_validate(parameters, arguments, path="arguments"))


_TYPE_CHECKS: Mapping[str, Callable[[object], bool]] = {
    "object": lambda v: isinstance(v, Mapping),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: (
        (isinstance(v, int) and not isinstance(v, bool))
        or (isinstance(v, float) and v.is_integer())
    ),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "null": lambda v: v is None,
}

_TYPE_MESSAGES = {
    "object": "JSON nesnesi olmalı",
    "array": "dizi olmalı",
    "string": "metin olmalı",
    "boolean": "boolean olmalı",
    "integer": "tam sayı olmalı",
    "number": "sayı olmalı",
    "null": "null olmalı",
}


def _matches_type(kinds: Sequence[object], value: object) -> bool:
    """`type` bir liste ise (`["string", "null"]`) değer biriyle uyuşmalı; bilinmeyen tip geçer."""
    for kind in kinds:
        check = _TYPE_CHECKS.get(str(kind))
        if check is None or check(value):  # bilinmeyen tip geçer
            return True
    return False


def _validate_combinators(schema: Mapping[str, object], value: object, path: str) -> list[str]:
    """`anyOf` en az bir, `oneOf` tam bir geçerli dal ister."""
    errors: list[str] = []
    for key in ("anyOf", "oneOf"):
        branches = schema.get(key)
        if not isinstance(branches, Sequence) or isinstance(branches, str | bytes):
            continue
        schemas = [b for b in branches if isinstance(b, Mapping)]
        matching = sum(not _validate(branch, value, path=path) for branch in schemas)
        if matching == 0:
            errors.append(f"{path}: izin verilen şemalardan hiçbirine uymuyor ({key})")
        elif key == "oneOf" and matching != 1:
            errors.append(f"{path}: yalnız bir şemaya uymalı (oneOf)")
    return errors


def _validate_bounds(schema: Mapping[str, object], value: object, path: str) -> list[str]:
    errors: list[str] = []
    minimum = schema.get("minimum")
    if (
        isinstance(minimum, int | float)
        and isinstance(value, int | float)
        and not isinstance(value, bool)
        and value < minimum
    ):
        errors.append(f"{path}: en az {minimum} olmalı")
    maximum = schema.get("maximum")
    if (
        isinstance(maximum, int | float)
        and isinstance(value, int | float)
        and not isinstance(value, bool)
        and value > maximum
    ):
        errors.append(f"{path}: en fazla {maximum} olmalı")
    min_items = schema.get("minItems")
    if isinstance(min_items, int) and isinstance(value, list) and len(value) < min_items:
        errors.append(f"{path}: en az {min_items} öğe içermeli")
    return errors


def _validate_object(
    schema: Mapping[str, object], value: Mapping[str, object], path: str
) -> list[str]:
    """Nesnenin zorunlu, tanımlı ve kapalı alan kısıtlarını uygula."""
    errors: list[str] = []
    required = schema.get("required", ())
    if isinstance(required, Sequence) and not isinstance(required, (str, bytes)):
        for field in required:
            if isinstance(field, str) and field not in value:
                errors.append(f"{path}.{field}: {MESSAGE_REQUIRED_MISSING}")
    raw_properties = schema.get("properties")
    properties = raw_properties if isinstance(raw_properties, Mapping) else {}
    for field, field_value in value.items():
        field_schema = properties.get(field)
        if isinstance(field_schema, Mapping):
            errors.extend(_validate(field_schema, field_value, path=f"{path}.{field}"))
        elif field not in properties and schema.get("additionalProperties") is False:
            errors.append(f"{path}.{field}: ek alana izin verilmiyor")
    return errors


def _validate(schema: Mapping[str, object], value: object, *, path: str) -> list[str]:
    errors = _validate_combinators(schema, value, path)
    kind = schema.get("type")
    if isinstance(kind, Sequence) and not isinstance(kind, str | bytes):
        if not _matches_type(kind, value):
            return [*errors, f"{path}: tür {list(kind)} içinden biri olmalı"]
    elif isinstance(kind, str):
        check = _TYPE_CHECKS.get(kind)
        if check is not None and not check(value):
            return [*errors, f"{path}: {_TYPE_MESSAGES[kind]}"]
    errors.extend(_validate_bounds(schema, value, path))
    if isinstance(value, Mapping):
        errors.extend(_validate_object(schema, value, path))
    elif isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                errors.extend(_validate(item_schema, item, path=f"{path}[{index}]"))

    enum = schema.get("enum")
    if (
        isinstance(enum, Sequence)
        and not isinstance(enum, (str, bytes))
        and not any(_json_equal(value, choice) for choice in enum)
    ):
        errors.append(f"{path}: izin verilen değerlerden biri olmalı: {list(enum)}")
    return errors


def _json_equal(left: object, right: object) -> bool:
    """Enum eşitliğinde JSON türlerini koru; boolean sayıyla eşleşemez."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(
            _json_equal(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(first, second) for first, second in zip(left, right, strict=True)
        )
    return type(left) is type(right) and left == right

"""JSON Şeması alt kümesiyle yapısal çıktı doğrulaması (yalnız stdlib).

`fusion agent --json-schema` (Claude Code `--json-schema`, Codex `--output-schema`) nihai
cevabın bir şemaya uymasını ister. Tam JSON Schema doğrulayıcısı üçüncü parti bağımlılık
getirirdi; betiklerin %95'inin kullandığı alt küme burada: `type`, `required`,
`properties`, `items`, `enum`, `additionalProperties: false`. Desteklenmeyen anahtarlar
sessizce yok sayılmaz, "doğrulanmadı" diye raporlanmaz — yalnız bilinen anahtarlar
denetlenir ve bu kısıt belgede yazılıdır (docs/HEADLESS.md).

Hata metinleri Türkçedir ve JSON yolunu (`$.ad`) taşır; model ya da betik hangi alanın
bozuk olduğunu görür.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

#: JSON Schema tip adı → kabul edilen Python tipleri.
_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list, tuple),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def validate_instance(instance: object, schema: Mapping[str, object], path: str = "$") -> list[str]:
    """Değeri şemaya göre denetle; hata listesi boşsa uyumludur."""
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None and not _matches_type(instance, expected):
        errors.append(
            f"{path}: beklenen tip {_type_label(expected)}, gelen {_python_label(instance)}"
        )
        return errors
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, str) and instance not in enum:
        errors.append(f"{path}: değer izin verilen seçeneklerden biri değil: {list(enum)!r}")
    if isinstance(instance, Mapping):
        errors.extend(_validate_object(instance, schema, path))
    elif isinstance(instance, (list, tuple)):
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(instance):
                errors.extend(validate_instance(item, items, f"{path}[{index}]"))
    return errors


def _validate_object(
    instance: Mapping[str, object], schema: Mapping[str, object], path: str
) -> list[str]:
    errors: list[str] = []
    required = schema.get("required")
    if isinstance(required, Sequence) and not isinstance(required, str):
        for name in required:
            if name not in instance:
                errors.append(f"{path}.{name}: zorunlu alan eksik")
    properties = schema.get("properties")
    known: Mapping[str, object] = properties if isinstance(properties, Mapping) else {}
    for name, sub_schema in known.items():
        if name in instance and isinstance(sub_schema, Mapping):
            errors.extend(validate_instance(instance[name], sub_schema, f"{path}.{name}"))
    if schema.get("additionalProperties") is False:
        for name in instance:
            if name not in known:
                errors.append(f"{path}.{name}: şemada tanımlı olmayan alan")
    return errors


def _matches_type(instance: object, expected: object) -> bool:
    names = (
        expected if isinstance(expected, Sequence) and not isinstance(expected, str) else [expected]
    )
    for name in names:
        accepted = _TYPES.get(str(name))
        if accepted is None:
            continue
        # JSON'da bool sayı değildir: `True` bir `integer`/`number` sayılmaz.
        if isinstance(instance, bool) and name in ("integer", "number"):
            continue
        if isinstance(instance, accepted):
            if name == "integer" and isinstance(instance, float):
                continue
            return True
    return False


def _type_label(expected: object) -> str:
    if isinstance(expected, Sequence) and not isinstance(expected, str):
        return "|".join(str(item) for item in expected)
    return str(expected)


def _python_label(instance: object) -> str:
    for name, accepted in _TYPES.items():
        if isinstance(instance, bool):
            return "boolean"
        if isinstance(instance, accepted):
            return name
    return type(instance).__name__

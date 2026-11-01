"""Uzak MCP araç şemasını ve açıklamasını sağlayıcıya göndermeden önce sadeleştirir.

Ölçüldü (29 Ekim): `inputSchema` olduğu gibi sağlayıcıya gidiyordu. `$ref`/`$defs`,
`anyOf`/`oneOf`, `additionalProperties`, `format` ve çok derin iç içe şemalar Gemini,
Mistral ve bazı ücretsiz OpenRouter modellerinde 400 ya da kötü araç çağrısı üretir;
`description` sınırsızdı (prompt bütçesi) ve araç açıklaması (`<important>…</important>`
gibi gizli talimat bloklarıyla) araç zehirlenmesine açıktı (M1-11).

Sadeleştirme DARDIR ve doğrulamayı gevşetir, sıkılaştırmaz: emin olunamayan yerde `type`
düşer (döngünün `validate_arguments`'ı tipsiz alanı doğrulamaz). Ham şema yalnız
sağlayıcıya giden kopya için değişir; uzak sunucu kendi doğrulamasını yapmaya devam eder.
"""

from __future__ import annotations

import os

import re
from collections.abc import Mapping, Sequence

__all__ = [
    "MAX_FIELD_DESCRIPTION_CHARS",
    "MAX_SCHEMA_DEPTH",
    "MAX_TOOL_DESCRIPTION_CHARS",
    "clean_description",
    "simplify_schema",
]

#: Araç açıklaması ve sunucu talimatı sınırı (Claude Code 4096; #262).
MAX_TOOL_DESCRIPTION_CHARS = 4096
#: Araç aramasıyla yüklenen açıklamanın sınırı (Claude Code 16384).
MAX_DEFERRED_DESCRIPTION_CHARS = 16384
DESCRIPTION_LENGTH_ENV = "CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH"
#: Tek alan açıklamasının en çok karakteri.
MAX_FIELD_DESCRIPTION_CHARS = 300
#: Bundan derin iç içe şema kesilir (`{"type": "object"}`).
MAX_SCHEMA_DEPTH = 6

#: Sağlayıcıların reddettiği ya da araç çağırmaya katkısı olmayan anahtarlar.
_STRIPPED_KEYS = frozenset(
    {
        "$schema",
        "$id",
        "$comment",
        "$defs",
        "definitions",
        "additionalProperties",
        "unevaluatedProperties",
        "patternProperties",
        "propertyNames",
        "format",
        "examples",
        "default",
        "title",
        "not",
        "if",
        "then",
        "else",
        "dependentRequired",
        "dependentSchemas",
        "contentEncoding",
        "contentMediaType",
        "readOnly",
        "writeOnly",
        "deprecated",
    }
)
_NULL_TYPE = "null"
_REF_PREFIXES = ("#/$defs/", "#/definitions/")

#: Araç zehirlenmesinde sık görülen gizli talimat blokları (en iyi çaba; tam çözüm değil).
_HIDDEN_BLOCK = re.compile(
    r"<\s*(important|system|instructions?|secret|hidden|override)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
#: Kontrol karakterleri ve sıfır genişlikli/yön değiştiren Unicode (görünmez talimat).
_INVISIBLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f​-‏‪-‮⁠-⁤﻿]")


def description_limit(*, deferred: bool = False, environ: Mapping[str, str] | None = None) -> int:
    """`CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` (yalın pozitif sayı) iki sınırı da değiştirir."""
    raw = (os.environ if environ is None else environ).get(DESCRIPTION_LENGTH_ENV, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return MAX_DEFERRED_DESCRIPTION_CHARS if deferred else MAX_TOOL_DESCRIPTION_CHARS


def clean_description(text: str, *, limit: int | None = None) -> str:
    """Açıklamadan gizli talimat bloklarını ve görünmez karakterleri at, sınırla."""
    cleaned = _INVISIBLE.sub("", _HIDDEN_BLOCK.sub("", text)).strip()
    return cleaned[: limit if limit is not None else description_limit()]


def simplify_schema(schema: Mapping[str, object]) -> dict[str, object]:
    """Şemayı sağlayıcı dostu, düz bir alt kümeye indir (girdi değiştirilmez)."""
    definitions = _collect_definitions(schema)
    simplified = _walk(schema, definitions, depth=0, seen=frozenset())
    if not isinstance(simplified, dict) or simplified.get("type") != "object":
        # Üst düzey nesne olmayan şema araç parametresi olamaz; boş nesneye düş.
        return {"type": "object", "properties": {}}
    return simplified


def _collect_definitions(schema: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    found: dict[str, Mapping[str, object]] = {}
    for key in ("$defs", "definitions"):
        block = schema.get(key)
        if isinstance(block, Mapping):
            for name, item in block.items():
                if isinstance(item, Mapping):
                    found[f"#/{key}/{name}"] = item
    return found


def _walk(
    node: object,
    definitions: Mapping[str, Mapping[str, object]],
    *,
    depth: int,
    seen: frozenset[str],
) -> object:
    if not isinstance(node, Mapping):
        return node
    if depth > MAX_SCHEMA_DEPTH:
        return {"type": "object"}
    ref = node.get("$ref")
    if isinstance(ref, str):
        target = definitions.get(ref) if ref.startswith(_REF_PREFIXES) else None
        if target is None or ref in seen:
            # Çözülemeyen ya da döngüsel başvuru: serbest nesne.
            return {"type": "object"}
        return _walk(target, definitions, depth=depth, seen=seen | {ref})
    merged = _merge_composition(node)
    result: dict[str, object] = {}
    for key, value in merged.items():
        if key in _STRIPPED_KEYS or key in ("anyOf", "oneOf", "allOf", "$ref"):
            continue
        if key == "type":
            kind = _single_type(value)
            if kind is not None:
                result["type"] = kind
        elif key == "properties" and isinstance(value, Mapping):
            result["properties"] = {
                name: _walk(item, definitions, depth=depth + 1, seen=seen)
                for name, item in value.items()
            }
        elif key == "items":
            result["items"] = _walk(value, definitions, depth=depth + 1, seen=seen)
        elif key == "description" and isinstance(value, str):
            result["description"] = clean_description(value, limit=MAX_FIELD_DESCRIPTION_CHARS)
        elif key == "const":
            result["enum"] = [value]
        elif key in ("required", "enum", "minimum", "maximum", "minItems", "maxItems"):
            result[key] = value
    return result


def _single_type(value: object) -> str | None:
    """`type` bir listeyse (['string', 'null']) boş olmayan tek tipe indir."""
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        kinds = [item for item in value if isinstance(item, str) and item != _NULL_TYPE]
        return kinds[0] if len(kinds) == 1 else None
    return None


def _merge_composition(node: Mapping[str, object]) -> dict[str, object]:
    """`allOf` nesne parçalarını birleştir; `anyOf`/`oneOf` tek biçime inerse onu al.

    Birden çok farklı biçim kalırsa `type` düşer (alan serbest kalır) ve açıklamaya not
    düşülür: yanlış tek tip dayatmak geçerli çağrıyı döngüde reddettirirdi.
    """
    merged: dict[str, object] = {k: v for k, v in node.items() if k not in ("allOf",)}
    all_of = node.get("allOf")
    if isinstance(all_of, Sequence) and not isinstance(all_of, (str, bytes)):
        properties: dict[str, object] = dict(_mapping(node.get("properties")))
        required: list[object] = list(_sequence(node.get("required")))
        for part in all_of:
            if isinstance(part, Mapping):
                properties.update(_mapping(part.get("properties")))
                required.extend(_sequence(part.get("required")))
        if properties:
            merged["type"] = "object"
            merged["properties"] = properties
            merged["required"] = list(dict.fromkeys(required))
    for key in ("anyOf", "oneOf"):
        variants = node.get(key)
        if not isinstance(variants, Sequence) or isinstance(variants, (str, bytes)):
            continue
        real = [
            v for v in variants if isinstance(v, Mapping) and _single_type(v.get("type")) != "null"
        ]
        if len(real) == 1:
            merged = {**dict(real[0]), **{k: v for k, v in merged.items() if k != key}}
        elif real:
            merged.pop("type", None)
            note = "birden çok biçim kabul eder"
            merged["description"] = f"{merged.get('description', '')} ({note})".strip()
    return merged


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()

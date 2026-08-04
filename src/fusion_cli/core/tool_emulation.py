"""Canonical emulated tool-call and raw payload formatting/parsing."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .types import ToolCall

CALL_OPEN = "<tool_call>"
CALL_CLOSE = "</tool_call>"
PAYLOAD_OPEN = "<tool_payload"
PAYLOAD_CLOSE = "</tool_payload>"

_BLOCK = re.compile(
    re.escape(CALL_OPEN) + r"(.*?)" + re.escape(CALL_CLOSE),
    re.DOTALL,
)
_PAYLOAD_ID = r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}"
_PAYLOAD_BLOCK = re.compile(
    rf'<tool_payload\s+id="(?P<id>{_PAYLOAD_ID})">'
    r"(?P<body>.*?)"
    + re.escape(PAYLOAD_CLOSE),
    re.DOTALL,
)


class _PayloadResolutionError(ValueError):
    """A payload reference could not be resolved safely."""


def _example_value(name: str, schema: Mapping[str, object]) -> object:
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes)) and enum:
        return enum[0]
    kind = schema.get("type")
    if kind == "boolean":
        return False
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "array":
        return []
    if kind == "object":
        return {}
    examples = {
        "path": "path/to/file",
        "content": "file content",
        "command": "python3 -m pytest -q",
        "pattern": "**/*.py",
        "query": "search query",
        "url": "https://example.com",
        "subcommand": "status",
    }
    return examples.get(name.lower(), "value")


def render_tool_example(function_schema: Mapping[str, object]) -> str:
    """Build one valid canonical short-call example from a function schema."""
    name = str(function_schema.get("name", "tool"))
    parameters = function_schema.get("parameters")
    arguments: dict[str, object] = {}
    if isinstance(parameters, Mapping):
        properties = parameters.get("properties")
        required = parameters.get("required")
        if (
            isinstance(properties, Mapping)
            and isinstance(required, Sequence)
            and not isinstance(required, (str, bytes))
        ):
            for field in required:
                if not isinstance(field, str):
                    continue
                raw_schema = properties.get(field, {})
                schema = raw_schema if isinstance(raw_schema, Mapping) else {}
                arguments[field] = _example_value(field, schema)
    payload = {"name": name, "arguments": arguments}
    return f"{CALL_OPEN}{json.dumps(payload, ensure_ascii=False)}{CALL_CLOSE}"


def render_tool_instructions(schemas: Sequence[Mapping[str, object]]) -> str:
    """Render the canonical short-call and raw-payload tool contract."""
    lines = [
        "Araç kullanacaksan yalnızca canonical blokları kullan:",
        (
            f'{CALL_OPEN}{{"name":"read_file","arguments":'
            f'{{"path":"src/app.py"}}}}{CALL_CLOSE}'
        ),
        (
            f'{CALL_OPEN}{{"name":"run_shell","arguments":'
            f'{{"command":"python3 -m pytest -q"}}}}{CALL_CLOSE}'
        ),
        "",
        "ÇOK SATIRLI / KOD İÇEREN write_file İÇİN ZORUNLU PAYLOAD BİÇİMİ:",
        '<tool_payload id="file-1">',
        "def greet(name: str) -> str:",
        '    return f"Hello, {name}!"',
        "</tool_payload>",
        (
            f"{CALL_OPEN}"
            + json.dumps(
                {
                    "name": "write_file",
                    "arguments": {
                        "path": "greet.py",
                        "content": {"$ref": "file-1"},
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + f"{CALL_CLOSE}"
        ),
        "",
        "Payload kuralları:",
        "- Kaynak kodu JSON content stringinin içine koyma.",
        "- Çok satırlı, tırnak veya ters eğik çizgi içeren content payload kullanmalı.",
        "- tool_payload içeriği ham metindir; JSON escape veya Markdown fence kullanma.",
        "- Her payload id benzersiz olmalı ve bir $ref ile kullanılmalı.",
        '- Payload referansı yalnızca {"$ref":"payload-id"} biçiminde olmalı.',
        "",
        "Genel kurallar:",
        "- name alanı zorunludur ve boş olamaz.",
        "- arguments alanı zorunludur ve her zaman JSON nesnesidir.",
        "- Şemadaki required alanlarının tamamını doğru tipte gönder.",
        "- Aynı çağrıyı aynı argümanlarla tekrar etme.",
        "- Araç kullanmayacaksan tool_call bloğu yazma; nihai cevabı ver.",
        "",
        "Kullanılabilir araçlar:",
    ]
    for schema in schemas:
        function = schema.get("function")
        if not isinstance(function, Mapping):
            continue
        name = function.get("name", "")
        description = function.get("description", "")
        parameters = function.get("parameters", {})
        lines.append(f"- {name}: {description}")
        lines.append(f"  parametreler: {json.dumps(parameters, ensure_ascii=False)}")
        lines.append(f"  kısa değer örneği: {render_tool_example(function)}")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class EmulatedParse:
    calls: tuple[ToolCall, ...]
    text: str
    errors: tuple[str, ...]


def _normalize_payload_body(body: str) -> str:
    """Remove only the framing line break around a canonical payload."""
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    if body.endswith("\r\n"):
        body = body[:-2]
    elif body.endswith("\n"):
        body = body[:-1]
    return body


def _resolve_payload_refs(
    value: object,
    payloads: Mapping[str, str],
    used: set[str],
    *,
    path: str,
) -> object:
    if isinstance(value, dict):
        if "$ref" in value:
            if set(value) != {"$ref"}:
                raise _PayloadResolutionError(
                    f"{path}: $ref nesnesi başka alan içeremez"
                )
            ref = value["$ref"]
            if not isinstance(ref, str) or not ref:
                raise _PayloadResolutionError(
                    f"{path}.$ref: boş olmayan metin olmalı"
                )
            if ref not in payloads:
                raise _PayloadResolutionError(
                    f"{path}.$ref: payload bulunamadı: {ref}"
                )
            used.add(ref)
            return payloads[ref]
        return {
            key: _resolve_payload_refs(
                item,
                payloads,
                used,
                path=f"{path}.{key}",
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_payload_refs(
                item,
                payloads,
                used,
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        ]
    return value


def parse_tool_calls(text: str) -> EmulatedParse:
    """Extract canonical calls and resolve raw payload references."""
    calls: list[ToolCall] = []
    errors: list[str] = []
    payloads: dict[str, str] = {}
    used_payloads: set[str] = set()

    for match in _PAYLOAD_BLOCK.finditer(text):
        payload_id = match.group("id")
        if payload_id in payloads:
            errors.append(f"yinelenen payload id: {payload_id}")
            continue
        payloads[payload_id] = _normalize_payload_body(match.group("body"))

    without_payloads = _PAYLOAD_BLOCK.sub("", text)
    if PAYLOAD_OPEN in without_payloads or PAYLOAD_CLOSE in without_payloads:
        errors.append("kapanmamış veya geçersiz tool_payload bloğu")

    for index, match in enumerate(_BLOCK.finditer(without_payloads)):
        raw = match.group(1).strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as error:
            errors.append(f"blok {index}: geçersiz JSON ({error.msg})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"blok {index}: çağrı bir JSON nesnesi olmalı")
            continue
        name = obj.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"blok {index}: 'name' alanı zorunlu ve boş olamaz")
            continue
        if "arguments" not in obj:
            errors.append(f"blok {index}: 'arguments' alanı zorunlu")
            continue
        arguments = obj["arguments"]
        if not isinstance(arguments, dict):
            errors.append(f"blok {index}: 'arguments' bir JSON nesnesi olmalı")
            continue
        try:
            resolved = _resolve_payload_refs(
                arguments,
                payloads,
                used_payloads,
                path=f"blok {index}.arguments",
            )
        except _PayloadResolutionError as error:
            errors.append(str(error))
            continue
        calls.append(
            ToolCall(
                id=f"emu-{index}",
                name=name.strip(),
                arguments=json.dumps(resolved, ensure_ascii=False),
            )
        )

    for payload_id in sorted(set(payloads) - used_payloads):
        errors.append(f"payload kullanılmadı: {payload_id}")

    outside = _BLOCK.sub("", without_payloads)
    if CALL_OPEN in outside or CALL_CLOSE in outside:
        errors.append("kapanmamış veya eşleşmeyen tool_call sınır işareti")

    return EmulatedParse(
        calls=tuple(calls),
        text=outside.strip(),
        errors=tuple(errors),
    )

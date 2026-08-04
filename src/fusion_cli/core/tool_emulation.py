"""Canonical emulated tool-call formatting and parsing."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .types import ToolCall

CALL_OPEN = "<tool_call>"
CALL_CLOSE = "</tool_call>"
_BLOCK = re.compile(re.escape(CALL_OPEN) + r"(.*?)" + re.escape(CALL_CLOSE), re.DOTALL)


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
    """Build one valid canonical example from a function schema."""
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
    """Render a short, valid and internally consistent tool contract."""
    lines = [
        "Araç kullanacaksan yalnızca geçerli JSON içeren canonical blok üret:",
        f'{CALL_OPEN}{{"name":"read_file","arguments":{{"path":"src/app.py"}}}}{CALL_CLOSE}',
        f'{CALL_OPEN}{{"name":"write_file","arguments":{{"path":"out.txt","content":"hello"}}}}{CALL_CLOSE}',
        (
            f'{CALL_OPEN}{{"name":"run_shell","arguments":'
            f'{{"command":"python3 -m pytest -q"}}}}{CALL_CLOSE}'
        ),
        "",
        "Zorunlu kurallar:",
        "- name alanı zorunludur ve boş olamaz.",
        "- arguments alanı zorunludur ve her zaman JSON nesnesidir.",
        "- Şemadaki required alanlarının tamamını doğru tipte gönder.",
        "- Aynı çağrıyı aynı argümanlarla tekrar etme.",
        "- Araç kullanmayacaksan tool_call bloğu yazma; doğrudan nihai cevabı ver.",
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
        lines.append(f"  geçerli örnek: {render_tool_example(function)}")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class EmulatedParse:
    calls: tuple[ToolCall, ...]
    text: str
    errors: tuple[str, ...]


def parse_tool_calls(text: str) -> EmulatedParse:
    """Extract only complete canonical calls and classify malformed blocks."""
    calls: list[ToolCall] = []
    errors: list[str] = []
    for index, match in enumerate(_BLOCK.finditer(text)):
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
        calls.append(
            ToolCall(
                id=f"emu-{index}",
                name=name.strip(),
                arguments=json.dumps(arguments, ensure_ascii=False),
            )
        )

    outside = _BLOCK.sub("", text)
    if CALL_OPEN in outside or CALL_CLOSE in outside:
        errors.append("kapanmamış veya eşleşmeyen tool_call sınır işareti")
    return EmulatedParse(calls=tuple(calls), text=outside.strip(), errors=tuple(errors))

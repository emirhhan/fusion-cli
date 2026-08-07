from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from fusion_cli.core.budget import TurnBudget
from fusion_cli.core.clock import SystemClock
from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.core.tool_emulation import (
    CALL_CLOSE,
    CALL_OPEN,
    PAYLOAD_OPEN,
    parse_tool_calls,
    render_tool_instructions,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import reflexion
from fusion_cli.engines.agent.approval import Decision
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _run_tools, _State
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential
from fusion_cli.tools import build_registry


class _Publisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class _Allow:
    async def decide(self, _request: object) -> Decision:
        return Decision.ALLOW


def _deps(tmp_path):
    # Bütçe sınırları geniş: bu dosya payload TAŞIMASINI sınar, bütçe tükenmesini
    # değil. Bütçenin kendi davranışı `test_turn_budget.py` içindedir.
    budget = TurnBudget(
        clock=SystemClock(),
        max_model_calls=50,
        max_verify_rounds=2,
        max_empty_retries=2,
        max_contract_repairs=1,
        max_auto_continues=1,
        max_idle_rounds=99,
    )
    return SimpleNamespace(
        publisher=_Publisher(),
        tool_context=ToolContext(tmp_path),
        policy=_Allow(),
        allowed_commands=frozenset(),
        budget=budget,
        require_budget=lambda: budget,
    )


def _payload_call(payload_id: str, path: str, content: str) -> str:
    call = {
        "name": "write_file",
        "arguments": {
            "path": path,
            "content": {"$ref": payload_id},
        },
    }
    # `lines` doğru davranan bir modelin yaptığı gibi gövdeden hesaplanır.
    satir_sayisi = len(content.splitlines())
    return (
        f'<tool_payload id="{payload_id}" lines="{satir_sayisi}">\n'
        f"{content}\n"
        "</tool_payload>\n"
        f"<tool_call>{json.dumps(call, ensure_ascii=False)}</tool_call>"
    )


def test_multiline_python_payload_resolves_without_json_escaping() -> None:
    source = (
        'def greet(name: str) -> str:\n'
        '    return f"Hello, {name}!"\n\n'
        'MESSAGE = "Ey Edip Adana\'da pide ye!"'
    )
    parsed = parse_tool_calls(_payload_call("source-1", "greet.py", source))

    assert not parsed.errors
    assert len(parsed.calls) == 1
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments == {"path": "greet.py", "content": source}


def test_two_payloads_resolve_to_two_write_calls() -> None:
    first = _payload_call(
        "source-1",
        "pkg/app.py",
        'print("first")',
    )
    second = _payload_call(
        "source-2",
        "pkg/test_app.py",
        'assert "a" == "a"',
    )
    parsed = parse_tool_calls(f"{first}\n{second}")

    assert not parsed.errors
    assert len(parsed.calls) == 2
    contents = [
        json.loads(call.arguments)["content"]
        for call in parsed.calls
    ]
    assert contents == ['print("first")', 'assert "a" == "a"']


def test_missing_payload_reference_is_rejected() -> None:
    raw = (
        '<tool_call>{"name":"write_file","arguments":'
        '{"path":"x.py","content":{"$ref":"missing"}}}</tool_call>'
    )
    parsed = parse_tool_calls(raw)

    assert not parsed.calls
    assert any("payload bulunamadı" in error for error in parsed.errors)


def test_duplicate_payload_id_is_rejected() -> None:
    raw = (
        '<tool_payload id="same" lines="1">\none\n</tool_payload>\n'
        '<tool_payload id="same" lines="1">\ntwo\n</tool_payload>\n'
        '<tool_call>{"name":"write_file","arguments":'
        '{"path":"x.txt","content":{"$ref":"same"}}}</tool_call>'
    )
    parsed = parse_tool_calls(raw)

    assert parsed.errors
    assert any("yinelenen payload id" in error for error in parsed.errors)


def test_unclosed_payload_is_rejected() -> None:
    raw = (
        '<tool_payload id="source-1" lines="1">\nprint("x")\n'
        '<tool_call>{"name":"write_file","arguments":'
        '{"path":"x.py","content":{"$ref":"source-1"}}}</tool_call>'
    )
    parsed = parse_tool_calls(raw)

    assert not parsed.calls
    assert any("payload" in error for error in parsed.errors)


def test_unused_payload_is_rejected() -> None:
    parsed = parse_tool_calls(
        '<tool_payload id="unused" lines="1">\nhello\n</tool_payload>'
    )

    assert not parsed.calls
    assert parsed.errors == ("payload kullanılmadı: unused",)


def test_payload_ref_object_cannot_have_extra_fields() -> None:
    raw = (
        '<tool_payload id="source-1" lines="1">\nhello\n</tool_payload>\n'
        '<tool_call>{"name":"write_file","arguments":'
        '{"path":"x.txt","content":{"$ref":"source-1","extra":true}}}'
        "</tool_call>"
    )
    parsed = parse_tool_calls(raw)

    assert not parsed.calls
    assert any("başka alan içeremez" in error for error in parsed.errors)


def test_legacy_short_inline_call_still_works() -> None:
    raw = (
        '<tool_call>{"name":"write_file","arguments":'
        '{"path":"x.txt","content":"hello"}}</tool_call>'
    )
    parsed = parse_tool_calls(raw)

    assert not parsed.errors
    assert json.loads(parsed.calls[0].arguments) == {
        "path": "x.txt",
        "content": "hello",
    }


def test_instructions_include_raw_payload_protocol() -> None:
    instructions = render_tool_instructions(build_registry().schemas())

    assert f'{PAYLOAD_OPEN} id="file-1"' in instructions
    assert '{"$ref":"file-1"}' in instructions
    assert "Kaynak kodu JSON content stringinin içine koyma; payload kullan." in instructions
    blocks = re.findall(
        rf"{CALL_OPEN}\s*(.*?)\s*{CALL_CLOSE}",
        instructions,
        flags=re.DOTALL,
    )
    assert blocks
    for block in blocks:
        json.loads(block)


def test_repair_note_teaches_payload_protocol() -> None:
    note = reflexion.tool_contract_repair_note(
        "TOOL_CALL_PARSE_ERROR: invalid JSON"
    )

    assert f'{PAYLOAD_OPEN} id="file-1"' in note.content
    assert '{"$ref":"file-1"}' in note.content
    assert "JSON stringine koyma" in note.content


def test_web_adapter_returns_resolved_payload_call() -> None:
    async def transport(*_args):
        return ""

    adapter = WebProviderAdapter(
        model="gemini_web/main/auto",
        credential=WebSessionCredential(),
        transport=transport,
        tool_support=ToolSupport.EMULATED,
    )
    raw = _payload_call(
        "source-1",
        "app.py",
        'print("hello")\nprint(\'world\')',
    )
    result = adapter._to_result(raw, latency_ms=1)

    assert result.ok
    assert result.error is None
    arguments = json.loads(result.tool_calls[0].arguments)
    assert arguments["content"] == 'print("hello")\nprint(\'world\')'


@pytest.mark.asyncio
async def test_resolved_payload_executes_write_file(tmp_path) -> None:
    source = 'def answer() -> str:\n    return "forty-two"'
    parsed = parse_tool_calls(
        _payload_call("source-1", "pkg/module.py", source)
    )
    assert not parsed.errors

    registry = build_registry()
    state = _State()
    messages: list[Message] = []
    execution = ExecutionPolicy(
        is_web=True,
        max_same_tool_without_change=2,
    )

    errored = await _run_tools(
        parsed.calls,
        messages,
        _deps(tmp_path),
        registry,
        state,
        execution=execution,
    )

    assert not errored
    assert (tmp_path / "pkg/module.py").read_text(encoding="utf-8") == source
    assert state.tool_calls_made == 1

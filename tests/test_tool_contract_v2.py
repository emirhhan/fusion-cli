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
    parse_tool_calls,
    render_tool_instructions,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent.approval import Decision
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _run_tools, _State
from fusion_cli.engines.effects.detect import required_effect_for
from fusion_cli.providers.web_browser import format_browser_prompt
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential
from fusion_cli.tools import build_registry
from fusion_cli.tools.emulation import validate_arguments


class _Publisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class _Allow:
    async def decide(self, _request: object) -> Decision:
        return Decision.ALLOW


def _deps(tmp_path, *, budget: TurnBudget | None = None):
    turn_budget = budget or _budget()
    return SimpleNamespace(
        publisher=_Publisher(),
        tool_context=ToolContext(tmp_path),
        policy=_Allow(),
        allowed_commands=frozenset(),
        budget=turn_budget,
        require_budget=lambda: turn_budget,
    )


def _budget(**overrides) -> TurnBudget:
    """Sözleşme testleri için geniş bir tur bütçesi.

    Sınırlar bilinçli olarak yüksek: bu dosya araç SÖZLEŞMESİNİ sınar, bütçe
    tükenmesini değil. Bütçenin kendi davranışı `test_turn_budget.py` içindedir.
    """
    limits = {
        "max_model_calls": 50,
        "max_verify_rounds": 2,
        "max_empty_retries": 2,
        "max_contract_repairs": 1,
        "max_auto_continues": 1,
        "max_idle_rounds": 99,
    }
    limits.update(overrides)
    return TurnBudget(clock=SystemClock(), **limits)


def test_instructions_contain_only_valid_canonical_examples() -> None:
    text = render_tool_instructions(build_registry().schemas())
    assert "{…}" not in text
    blocks = re.findall(
        rf"{CALL_OPEN}\s*(.*?)\s*{CALL_CLOSE}", text, flags=re.DOTALL
    )
    assert blocks
    for block in blocks:
        payload = json.loads(block)
        assert isinstance(payload["name"], str)
        assert isinstance(payload["arguments"], dict)


def test_parser_rejects_missing_arguments() -> None:
    parsed = parse_tool_calls('<tool_call>{"name":"write_file"}</tool_call>')
    assert not parsed.calls
    assert any("arguments" in error for error in parsed.errors)


def test_parser_rejects_unclosed_block() -> None:
    parsed = parse_tool_calls('<tool_call>{"name":"read_file","arguments":{}}')
    assert not parsed.calls
    assert parsed.errors


def test_schema_validation_catches_required_and_type_errors() -> None:
    registry = build_registry()
    write_file = registry.get("write_file")
    assert write_file is not None
    function = write_file.schema()["function"]
    assert isinstance(function, dict)
    errors = validate_arguments(function, {"content": "hello"})
    assert any("path" in error for error in errors)
    errors = validate_arguments(function, {"path": 3, "content": "hello"})
    assert any("metin" in error for error in errors)


def test_web_adapter_surfaces_parse_error_without_provider_fallback() -> None:
    async def transport(*_args):
        return ""

    adapter = WebProviderAdapter(
        model="gemini_web/main/auto",
        credential=WebSessionCredential(),
        transport=transport,
        tool_support=ToolSupport.EMULATED,
    )
    result = adapter._to_result(
        '<tool_call>{"name":"run_shell"}</tool_call>',
        latency_ms=1,
    )
    assert result.ok
    assert result.error is not None
    assert result.error.startswith("TOOL_CALL_PARSE_ERROR")
    assert not result.tool_calls


def test_browser_history_preserves_arguments() -> None:
    messages = (
        Message(
            "assistant",
            "",
            tool_calls=(
                ToolCall(
                    id="1",
                    name="write_file",
                    arguments='{"path":"a.txt","content":"hello"}',
                ),
            ),
        ),
    )
    rendered = format_browser_prompt(messages)
    assert "name: write_file" in rendered
    assert '"path":"a.txt"' in rendered
    assert '"content":"hello"' in rendered


def test_negated_git_clause_does_not_route_to_push() -> None:
    effect = required_effect_for(
        "Git komutu çalıştırma. GitHub işlemi yapma. fusion_test klasörü oluştur."
    )
    assert effect == "workspace_mutation"


def test_negative_file_instruction_is_not_positive_mutation() -> None:
    task = "Dosya oluşturma veya değiştirme. Yalnız cevap ver."
    assert required_effect_for(task) is None


def test_explicit_no_tools_does_not_erase_positive_push() -> None:
    task = "repoyu GitHub'a pushla ama araç kullanma"
    assert required_effect_for(task) == "git_push"


def test_positive_push_still_routes_to_git_push() -> None:
    assert required_effect_for("Repoyu GitHub'a pushla") == "git_push"


@pytest.mark.asyncio
async def test_second_invalid_call_aborts_even_if_tool_changes(tmp_path) -> None:
    registry = build_registry()
    deps = _deps(tmp_path)
    state = _State()
    messages: list[Message] = []
    execution = ExecutionPolicy(is_web=True, max_same_tool_without_change=2)

    first = ToolCall(id="1", name="write_file", arguments="{}")
    assert await _run_tools(
        (first,), messages, deps, registry, state, execution=execution
    )
    # Onarım hakkı artık TUR bütçesindedir; tek bir `_drive` çağrısının değil.
    assert deps.budget.contract_repairs == 1
    assert not state.tool_contract_abort

    second = ToolCall(id="2", name="run_shell", arguments="{}")
    assert await _run_tools(
        (second,), messages, deps, registry, state, execution=execution
    )
    assert state.tool_contract_abort.startswith("TOOL_CALL_ABORTED")


@pytest.mark.asyncio
async def test_third_successful_read_is_stopped(tmp_path) -> None:
    (tmp_path / "input.txt").write_text("hello", encoding="utf-8")
    registry = build_registry()
    deps = _deps(tmp_path)
    state = _State()
    messages: list[Message] = []
    execution = ExecutionPolicy(is_web=True, max_same_tool_without_change=2)
    raw = '{"path":"input.txt"}'

    first = ToolCall(id="1", name="read_file", arguments=raw)
    second = ToolCall(id="2", name="read_file", arguments=raw)
    third = ToolCall(id="3", name="read_file", arguments=raw)

    assert not await _run_tools(
        (first,), messages, deps, registry, state, execution=execution
    )
    assert not await _run_tools(
        (second,), messages, deps, registry, state, execution=execution
    )
    assert await _run_tools(
        (third,), messages, deps, registry, state, execution=execution
    )
    assert "TOOL_CALL_DUPLICATE" in state.tool_contract_abort


@pytest.mark.asyncio
async def test_second_identical_mutation_is_stopped(tmp_path) -> None:
    registry = build_registry()
    deps = _deps(tmp_path)
    state = _State()
    messages: list[Message] = []
    execution = ExecutionPolicy(is_web=True, max_same_tool_without_change=2)
    raw = json.dumps({"command": "python3 -c 'print(1)'"})

    first = ToolCall(id="1", name="run_shell", arguments=raw)
    second = ToolCall(id="2", name="run_shell", arguments=raw)

    assert not await _run_tools(
        (first,), messages, deps, registry, state, execution=execution
    )
    assert await _run_tools(
        (second,), messages, deps, registry, state, execution=execution
    )
    assert "TOOL_CALL_DUPLICATE" in state.tool_contract_abort

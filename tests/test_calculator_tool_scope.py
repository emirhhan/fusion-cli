"""Dondurulmuş Calculator istemleri için gerçek tur şeması ve araç kapısı."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolResult
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.expertise import is_desktop_task
from fusion_cli.engines.agent.tool_constraints import NATIVE_METHOD_BLOCKED
from fusion_cli.mcp_bridge.discovery import McpDiscovery
from fusion_cli.tools import desktop_policy

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur

# frozen-29f0a999/native/calculator-guided-start.json ve calculator-buttons-start.json
GUIDED = (
    "Yalniz Hesap Makinesi: 29 arti 48 hesapla, sonucu ekrandan dogrula. "
    "desktop_window_focus ile Calculator kimligini al. "
    "Her basistan once desktop_background_inspect ile ayni pencereyi incele. "
    "Yalniz guncel gorunen dugme refiyle desktop_background_action press kullan. "
    "Klavye, kisayol, yazi, yapistirma, kod, set_value ve koordinat kullanma. "
    "Baska uygulamaya dokunma."
)
BUTTONS = (
    "Yalniz Hesap Makinesi uygulamasinda 29 arti 48 hesapla. "
    "Sadece gorunen dugmelere tikla. Klavye tusu, kisayol, yazi yazma, yapistirma veya kod "
    "kullanma. Sonucu ekrandan dogrula; baska uygulamalarda islem yapma."
)
WINDOW = {"pid": 20, "window_id": 2}
FOCUS = "desktop_window_focus"
INSPECT = "desktop_background_inspect"
ACTION = "desktop_background_action"
CLICK = "desktop_click"
MOUSE = "desktop_mouse"
SCROLL = "desktop_scroll"


def _calculator_deps(tmp_path, monkeypatch):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    deps.mcp_discovery = McpDiscovery(lambda: deps.config, root=tmp_path)
    deps.config = replace(deps.config, desktop=replace(deps.config.desktop, enabled=True))
    monkeypatch.setattr(loop, "_publish_intro", AsyncMock(return_value=None))
    monkeypatch.setattr(
        desktop_policy,
        "_swift_probe",
        AsyncMock(
            return_value={
                "ok": True,
                "app": "Calculator",
                "bundle": "com.apple.calculator",
                "pid": WINDOW["pid"],
            }
        ),
    )
    handlers = {}
    for name, output in (
        (FOCUS, ToolResult("Calculator", structured={"target": WINDOW})),
        (INSPECT, ToolResult("Calculator: AXButton 2 (current-ref)")),
        (ACTION, ToolResult("AXPress tamamlandı")),
        (CLICK, None),
        (MOUSE, None),
        (SCROLL, ToolResult("Kaydırıldı")),
        ("desktop_type", None),
        ("desktop_key", None),
        ("run_shell", None),
    ):
        handler = AsyncMock(
            return_value=output,
            side_effect=AssertionError(f"Yasak yöntem çalıştı: {name}") if output is None else None,
        )
        registry = deps.base_registry
        assert registry is not None
        tool = registry.get(name)
        assert tool is not None
        registry.register_or_replace(replace(tool, run=handler))
        handlers[name] = handler
    return deps, sink, handlers


@pytest.mark.parametrize("task", [GUIDED, BUTTONS], ids=["guided", "visible-buttons"])
async def test_calculator_turn_exposes_and_dispatches_native_inspect_and_press(
    tmp_path, monkeypatch, task
):
    action = {**WINDOW, "action": "press", "ref": "current-ref"}
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call(FOCUS, app="Calculator")]),
            model_result(tool_calls=[tool_call(INSPECT, **WINDOW)]),
            model_result(tool_calls=[tool_call(ACTION, **action)]),
            model_result("Hesap Makinesi düğmesine basıldı."),
        ]
    )
    _kur(monkeypatch, provider)
    deps, sink, handlers = _calculator_deps(tmp_path, monkeypatch)

    await loop.run_agent(task, deps, self_review=False, verify=False)

    schemas = {schema["function"]["name"] for schema in provider.seen_requests[0]}
    executions = {
        event.name: event.outcome for event in sink.events if isinstance(event, ToolExecuted)
    }
    assert executions == {FOCUS: ToolOutcome.OK, INSPECT: ToolOutcome.OK, ACTION: ToolOutcome.OK}
    assert {FOCUS, INSPECT, ACTION} <= schemas
    assert not schemas & {"run_shell", "bash", "desktop_type", "desktop_key"}
    assert (schemas & {CLICK, MOUSE}) == (set() if task == GUIDED else {CLICK, MOUSE})
    assert SCROLL in schemas
    assert handlers[INSPECT].await_args.args[0] == WINDOW
    assert handlers[ACTION].await_args.args[0] == action


async def test_calculator_turn_blocks_prohibited_method_routes_before_dispatch(
    tmp_path, monkeypatch
):
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("desktop_type", text="29+48")]),
            model_result(tool_calls=[tool_call("desktop_key", key="cmd+v")]),
            model_result(tool_calls=[tool_call("run_shell", command="exit 0")]),
            model_result(
                tool_calls=[
                    tool_call(ACTION, **WINDOW, ref="current-ref", action="set_value", value="77")
                ]
            ),
            model_result("İstenen yöntem sınırı korundu."),
        ]
    )
    _kur(monkeypatch, provider)
    deps, sink, handlers = _calculator_deps(tmp_path, monkeypatch)

    await loop.run_agent(GUIDED, deps, self_review=False, verify=False)

    executed = [
        (event.name, event.outcome) for event in sink.events if isinstance(event, ToolExecuted)
    ]
    assert executed == [
        ("desktop_type", ToolOutcome.BLOCKED),
        ("desktop_key", ToolOutcome.BLOCKED),
        ("run_shell", ToolOutcome.BLOCKED),
        (ACTION, ToolOutcome.BLOCKED),
    ]
    for name, _ in executed:
        handlers[name].assert_not_awaited()


async def test_guided_turn_blocks_coordinate_routes_but_preserves_relative_scroll(
    tmp_path, monkeypatch
):
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call(CLICK, x=10, y=10)]),
            model_result(tool_calls=[tool_call(MOUSE, action="hover", x=10, y=10)]),
            model_result(tool_calls=[tool_call(SCROLL, lines=1, x=10, y=10)]),
            model_result(tool_calls=[tool_call(SCROLL, lines=1)]),
            model_result("Koordinat gerektirmeyen kaydırma çalıştı."),
        ]
    )
    _kur(monkeypatch, provider)
    deps, sink, handlers = _calculator_deps(tmp_path, monkeypatch)

    await loop.run_agent(GUIDED, deps, self_review=False, verify=False)

    events = [event for event in sink.events if isinstance(event, ToolExecuted)]
    assert [(event.name, event.outcome) for event in events] == [
        (CLICK, ToolOutcome.BLOCKED),
        (MOUSE, ToolOutcome.BLOCKED),
        (SCROLL, ToolOutcome.BLOCKED),
        (SCROLL, ToolOutcome.OK),
    ]
    assert events[2].output == NATIVE_METHOD_BLOCKED
    handlers[CLICK].assert_not_awaited()
    handlers[MOUSE].assert_not_awaited()
    assert [call.args[0] for call in handlers[SCROLL].await_args_list] == [{"lines": 1}]


@pytest.mark.parametrize("prohibition", ["Do not use `set_value`.", "set_value kullanma."])
async def test_direct_set_value_prohibition_preserves_press_schema_and_dispatch(
    tmp_path, monkeypatch, prohibition
):
    press = {**WINDOW, "ref": "current-ref", "action": "press"}
    provider = ScriptedProvider(
        [
            model_result(
                tool_calls=[tool_call(ACTION, **{**press, "action": "set_value", "value": "77"})]
            ),
            model_result(tool_calls=[tool_call(ACTION, **press)]),
            model_result("Düğmeye basıldı."),
        ]
    )
    _kur(monkeypatch, provider)
    deps, sink, handlers = _calculator_deps(tmp_path, monkeypatch)

    await loop.run_agent(
        f"Call desktop_background_action on Calculator. {prohibition}",
        deps,
        self_review=False,
        verify=False,
    )

    assert ACTION in {schema["function"]["name"] for schema in provider.seen_requests[0]}
    events = [event for event in sink.events if isinstance(event, ToolExecuted)]
    assert [(event.name, event.outcome) for event in events] == [
        (ACTION, ToolOutcome.BLOCKED),
        (ACTION, ToolOutcome.OK),
    ]
    assert events[0].output == NATIVE_METHOD_BLOCKED
    assert [call.args[0] for call in handlers[ACTION].await_args_list] == [press]


@pytest.mark.parametrize(
    ("task", "limits"),
    [
        ("29 artı 48 kaç eder?", {}),
        (GUIDED, {"allowed_tools": {FOCUS}}),
        (GUIDED, {"denied_tools": frozenset({INSPECT, ACTION})}),
    ],
    ids=["unrelated", "caller-allowlist", "caller-denylist"],
)
async def test_native_scope_respects_unrelated_task_and_explicit_tool_limits(
    tmp_path, monkeypatch, task, limits
):
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call(INSPECT, **WINDOW)]),
            model_result("İnceleme yapılamadı."),
        ]
    )
    _kur(monkeypatch, provider)
    deps, sink, handlers = _calculator_deps(tmp_path, monkeypatch)

    await loop.run_agent(task, deps, self_review=False, verify=False, **limits)

    schemas = {schema["function"]["name"] for schema in provider.seen_requests[0]}
    assert not schemas & {INSPECT, ACTION}
    assert [
        (event.name, event.outcome) for event in sink.events if isinstance(event, ToolExecuted)
    ] == [(INSPECT, ToolOutcome.BLOCKED)]
    handlers[INSPECT].assert_not_awaited()


@pytest.mark.parametrize(
    "task",
    [
        "Call `desktop_background_inspect` on the selected window ID.",
        "desktop_background_inspect ile aynı pencereyi incele.",
        "Hesap Makinesi uygulamasında görünen düğmeye tıkla.",
        "Hesap Makinesi uygulamasında görünen düğmeye tıkla. Ardından Python kodu yaz.",
        "Click the visible buttons in the Calculator app.",
    ],
)
def test_explicit_native_interactions_are_desktop_tasks(task):
    assert is_desktop_task(task)


@pytest.mark.parametrize(
    "task",
    [
        "desktop_background_inspect",
        "What does `desktop_background_inspect` do?",
        "Read `first; use desktop_background_inspect` as plain text.",
        'Explain "use desktop_background_inspect".',
        "> Use desktop_background_inspect.\nBunu açıkla.",
        "```text\nUse desktop_background_inspect.\n```\nBunu açıkla.",
        "Use desktop_background_inspect_backup for your Python example.",
        "Use desktop_background_inspect.json to review the fixture.",
        "desktop_background_inspect kullanma.",
        "29 artı 48 hesapla.",
        "Build a calculator app in Python.",
        "Build a Calculator app. Click the visible buttons to test it.",
        "Hesap Makinesi uygulaması geliştir.",
        "Hesap Makinesi mobil uygulamasında görünen düğmelere tıkla.",
        "Hesap Makinesi web uygulamasında görünen düğmelere tıkla.",
        "Click the visible buttons in the web Calculator app.",
    ],
)
def test_mentions_and_non_native_calculator_tasks_do_not_open_desktop_scope(task):
    assert not is_desktop_task(task)

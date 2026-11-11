from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.approval import Allowance, ApprovalRequest
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.hook_bridge import ToolGate
from fusion_cli.tools import build_registry, desktop, native_desktop

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur

TASK = (
    "Yalniz yerel uygulama ile 29 arti 48 hesapla. Fareyle veya AXPress kullan. "
    "Klavye tusu, kisayol, yazi yazma, yapistirma veya kod kullanma. "
    "Baska uygulama veya web sayfasi acma."
)


@pytest.mark.parametrize("task", [TASK, TASK.replace("Klavye tusu", "KLAVYE TUŞU")])
def test_native_method_prohibition_maps_actual_routes(task):
    from fusion_cli.engines.agent.tool_constraints import native_method_denials

    denied = native_method_denials(task)
    assert {
        "desktop_key",
        "desktop_type",
        "desktop_background_action:set_value",
        "run_shell",
    } <= denied
    assert "desktop_background_action" not in denied


@pytest.mark.parametrize(
    "task",
    [
        "Do not use keyboard or shortcuts.",
        "Never press keys.",
        "Klavye kullanma.",
        "Klavye tuşlarına basma.",
        "Kısayol kullanma.",
    ],
)
def test_direct_keyboard_prohibitions_cover_both_native_event_routes(task):
    from fusion_cli.engines.agent.tool_constraints import native_method_denials

    assert {"desktop_key", "desktop_type"} <= native_method_denials(task)


@pytest.mark.parametrize(
    ("args", "blocked"),
    [
        ({"key": "cmd+v"}, True),
        ({"key": "v", "control": True}, True),
        ({"key": "cmd+shift+v"}, True),
        ({"key": "cmd+a"}, False),
        ({"key": "v"}, False),
    ],
)
def test_paste_only_restriction_preserves_other_keys(args, blocked):
    from fusion_cli.engines.agent.tool_constraints import (
        native_method_blocked,
        native_method_denials,
    )

    denied = native_method_denials("Do not paste.")
    assert native_method_blocked("desktop_key", args, denied) is blocked
    assert "desktop_key" not in denied and "desktop_type" not in denied


@pytest.mark.parametrize(
    "task",
    [
        'Açıklama: "Klavye kullanma". Klavyeyi kullan.',
        "```text\nKlavye kullanma.\n```\nFare kullan.",
        "> Klavye kullanma.\nKlavye kullan.",
        "Örnek: klavye kullanma.\nFare kullan.",
        "Klavye kullanma demedim.",
        "Klavye kullanmak yasak değil.",
        "If the hypothetical user says do not use keyboard, explain the phrase.",
        "Do not use keyboard is not my instruction.",
        "Klavye kullanma demedim, fare kullanma.",
        "Python dosyasını düzenle. Kod kullanma.",
        "Klavye kullan; AXPress başarısızsa klavyeyle devam et.",
        'Masaüstünde devam et. Açıklama: "Koordinat ve set_value kullanma".',
        'Masaüstünde devam et. "Do not use `set_value`" metnini açıkla.',
        'Hesap Makinesi uygulamasını aç. "Koordinat ve set_value kullanma" ifadesini açıkla.',
        '"Hesap Makinesi uygulamasını aç." ifadesini açıkla. Koordinat ve set_value kullanma.',
        "Masaüstünde devam et. Örnek: koordinat ve set_value kullanma.",
        "Masaüstünde devam et. Koordinat ve set_value kullanma demedim.",
        "GeoJSON dosyasını düzenle. Koordinat ve set_value kullanma.",
    ],
)
def test_examples_meta_negations_and_unrelated_code_do_not_derive_denials(task):
    from fusion_cli.engines.agent.tool_constraints import native_method_denials

    assert not native_method_denials(task)


@pytest.mark.parametrize("prohibition", ["No coordinates.", "Koordinatları kullanma, devam et."])
def test_native_coordinate_prohibition_distinguishes_positioned_scroll(prohibition):
    from fusion_cli.engines.agent.tool_constraints import (
        native_method_blocked,
        native_method_denials,
    )

    denied = native_method_denials(f"Call desktop_background_inspect. {prohibition}")
    assert {"desktop_click", "desktop_mouse"} <= denied
    assert "desktop_scroll" not in denied
    assert native_method_blocked("desktop_scroll", {"x": 0}, denied)
    assert native_method_blocked("desktop_scroll", {"y": 0}, denied)
    assert not native_method_blocked("desktop_scroll", {"lines": 1}, denied)


@pytest.mark.parametrize("context", ["Hesap Makinesi uygulamasını aç.", "Masaüstünde devam et."])
def test_direct_native_context_projects_route_denials_without_extending_shell_denial(context):
    from fusion_cli.engines.agent.tool_constraints import (
        native_method_blocked,
        native_method_denials,
    )

    denied = native_method_denials(f"{context} Koordinat, set_value ve kod kullanma.")
    assert {"desktop_click", "desktop_mouse"} <= denied
    assert "run_shell" not in denied
    assert native_method_blocked("desktop_scroll", {"x": 0, "y": 0}, denied)
    assert native_method_blocked("desktop_background_action", {"action": "set_value"}, denied)
    assert not native_method_blocked("desktop_background_action", {"action": "press"}, denied)


async def test_fake_real_engine_cannot_execute_explicitly_prohibited_key(tmp_path, monkeypatch):
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("desktop_key", key="cmd+a")]),
            model_result("Klavye yöntemi engellendi; işlem tamamlanmadı."),
        ]
    )
    _kur(monkeypatch, provider)
    monkeypatch.setattr(loop, "_publish_intro", AsyncMock(return_value=None))
    native = AsyncMock(side_effect=AssertionError("native must not run"))
    monkeypatch.setattr(desktop, "_send_chords", native)
    approval = AsyncMock(side_effect=AssertionError("approval must not run"))
    monkeypatch.setattr(loop, "resolve_request", approval)
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    deps.config = replace(deps.config, desktop=replace(deps.config.desktop, enabled=True))
    await loop.run_agent(
        TASK,
        deps,
        self_review=False,
        verify=False,
        allowed_tools={"desktop_key", "desktop_background_action"},
    )
    events = [event for event in sink.events if isinstance(event, ToolExecuted)]
    assert events and events[0].outcome is ToolOutcome.BLOCKED
    native.assert_not_called()
    approval.assert_not_called()


@pytest.mark.parametrize("rewrite", ["direct", "hook", "approval"])
async def test_mode_denial_checks_effective_action_before_native(tmp_path, monkeypatch, rewrite):
    deps = _deps(tmp_path, RecordingSink())
    deps.denied_tools = frozenset({"desktop_background_action:set_value"})
    deps.budget = loop._new_budget(deps.config)
    deps.tool_context.task_kinds.add("masaustu")
    args = {"pid": 20, "window_id": 2, "ref": "legacy-ref", "action": "press"}
    replacement = {**args, "action": "set_value", "value": "77"}
    if rewrite == "direct":
        args = replacement
    elif rewrite == "hook":
        monkeypatch.setattr(loop, "pre_tool_use", AsyncMock(return_value=ToolGate(replacement)))
    else:
        from types import SimpleNamespace

        monkeypatch.setattr(
            loop,
            "_current_policy",
            lambda _deps: SimpleNamespace(decide=AsyncMock(return_value=Allowance(replacement))),
        )
    seen = []

    async def approve(tool, values, *_args, **_kwargs):
        seen.append(values)
        assert values["action"] == "press", "rewritten prohibited action reached permission"
        return ApprovalRequest(tool, values, danger=None, pre_allowed=True)

    monkeypatch.setattr(loop, "resolve_request", approve)
    native = AsyncMock(side_effect=AssertionError("native must not run"))
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", native)
    result, outcome = await loop._execute(
        tool_call("desktop_background_action", **args),
        args,
        deps,
        build_registry(),
        execution=ExecutionPolicy(is_web=False),
    )
    assert not result.ok and outcome is ToolOutcome.BLOCKED
    assert len(seen) == (1 if rewrite == "approval" else 0)
    native.assert_not_called()


async def test_new_root_turn_restores_caller_ceiling_and_children_inherit(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.agent_task_tools import _inherited_limits
    from fusion_cli.engines.agent.team import SubTask

    deps = _deps(tmp_path, RecordingSink())
    deps.denied_tools = frozenset({"desktop_type"})
    seen = []

    async def turn(task, *, deps, **kwargs):
        if kwargs.get("depth", 0) == 1:
            assert {"desktop_key", "desktop_type", "read_file"} <= deps.denied_tools
            return loop.AgentOutcome("child fixture finished", [])
        seen.append(deps.denied_tools)
        _root, options = _inherited_limits(deps, SubTask(task="child keyboard allowed"))
        assert set(options.denied_tools) >= deps.denied_tools
        # Even an explicitly permissive child prompt cannot change the parent ceiling.
        if len(seen) == 1:
            child = replace(deps, channel=loop.Channel.SUBAGENT)
            await loop.run_agent("Klavyeyi kullanabilirsin.", child, depth=1, self_review=False)
            assert child.denied_tools == deps.denied_tools
        return loop.AgentOutcome("bounded fixture finished", [])

    monkeypatch.setattr(loop, "_run_agent", turn)
    await loop.run_agent(TASK, deps, denied_tools=frozenset({"read_file"}), self_review=False)
    assert {"desktop_key", "desktop_type", "read_file"} <= seen[0]
    assert deps.denied_tools == {"desktop_type"}
    await loop.run_agent("Fare ve klavye kullanabilirsin.", deps, self_review=False)
    assert seen[1] == {"desktop_type"}
    assert deps.denied_tools == {"desktop_type"}


async def test_exception_restores_only_scoped_additions(tmp_path, monkeypatch):
    deps = _deps(tmp_path, RecordingSink())
    deps.denied_tools = frozenset({"read_file"})

    async def fail(*_args, **_kwargs):
        assert "desktop_key" in deps.denied_tools
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(loop, "_run_agent", fail)
    with pytest.raises(RuntimeError, match="fixture failure"):
        await loop.run_agent(TASK, deps, self_review=False)
    assert deps.denied_tools == {"read_file"}


async def test_text_input_denial_still_allows_press_to_native_guard(tmp_path, monkeypatch):
    deps = _deps(tmp_path, RecordingSink())
    deps.denied_tools = frozenset({"desktop_background_action:set_value"})
    deps.budget = loop._new_budget(deps.config)
    deps.tool_context.task_kinds.add("masaustu")
    args = {"pid": 20, "window_id": 2, "ref": "legacy-full-reference", "action": "press"}

    async def approve(tool, values, *_args, **_kwargs):
        return ApprovalRequest(tool, values, danger=None, pre_allowed=True)

    monkeypatch.setattr(loop, "resolve_request", approve)
    invoke = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result, outcome = await loop._execute(
        tool_call("desktop_background_action", **args),
        args,
        deps,
        build_registry(),
        execution=ExecutionPolicy(is_web=False),
    )
    assert result.ok and outcome is ToolOutcome.OK
    assert invoke.call_args.args[1]["request"]["ref"] == args["ref"]


def test_press_and_default_native_methods_remain_available():
    from fusion_cli.engines.agent.tool_constraints import native_method_blocked

    assert not native_method_blocked(
        "desktop_background_action", {"action": "press"}, {"desktop_background_action:set_value"}
    )
    assert not native_method_blocked("desktop_key", {"key": "cmd+v"}, set())


async def test_actual_child_construction_preserves_route_denials(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.team import SubTask, run_subagent

    deps = _deps(tmp_path, RecordingSink())
    deps.denied_tools = frozenset({"desktop_key", "desktop_background_action:set_value"})
    deps.budget = loop._new_budget(deps.config)

    async def child_run(task, child, **_kwargs):
        assert deps.denied_tools <= child.denied_tools
        args = {"pid": 20, "window_id": 2, "ref": "full-ref", "action": "set_value", "value": "77"}
        _result, outcome = await loop._execute(
            tool_call("desktop_background_action", **args),
            args,
            child,
            build_registry(),
            execution=ExecutionPolicy(is_web=False),
        )
        assert outcome is ToolOutcome.BLOCKED
        return loop.AgentOutcome("child denied fixture", [])

    invoke = AsyncMock(side_effect=AssertionError("native must not run"))
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await run_subagent(
        deps, SubTask("Klavye ve yazı serbest."), depth=0, run_agent=child_run
    )
    assert result.ok, result.text
    invoke.assert_not_called()


async def test_main_persona_denial_is_a_ceiling(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.team import GENERIC_PERSONA

    deps = _deps(tmp_path, RecordingSink())
    deps.session_persona = replace(GENERIC_PERSONA, disallowed_tools=frozenset({"desktop_key"}))
    seen = []

    async def turn(task, *, deps, **_kwargs):
        seen.append(deps.denied_tools)
        return loop.AgentOutcome("persona fixture", [])

    monkeypatch.setattr(loop, "_run_agent", turn)
    await loop.run_agent("Klavye kullanabilirsin.", deps, self_review=False)
    assert "desktop_key" in seen[0]


@pytest.mark.parametrize(
    ("task", "required"),
    [
        ("Metin yazma, fareyle devam et.", {"desktop_type", "desktop_background_action:set_value"}),
        ("Yapıştırma, fareyle devam et.", {"desktop_key:paste"}),
        ("Klavye tuşlarına basma, fareyle devam et.", {"desktop_key", "desktop_type"}),
    ],
)
def test_turkish_method_negative_closes_before_comma(task, required):
    from fusion_cli.engines.agent.tool_constraints import native_method_denials

    assert required <= native_method_denials(task)

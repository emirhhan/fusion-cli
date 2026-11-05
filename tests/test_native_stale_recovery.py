"""Repeated rejected native targets need a different method, not another ref nonce."""

from __future__ import annotations

import base64
import json
from dataclasses import replace

import pytest

from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolResult
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import engine_tools, loop
from fusion_cli.engines.agent.approval import ApprovalRequest
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.tools import build_registry, desktop, desktop_mouse, native_desktop

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur


def ref(nonce, *, pid=20, window=2, identity="AXButton\x1f\x1fThree\x1f3"):
    return base64.b64encode(
        json.dumps(
            {
                "pid": pid,
                "id": window,
                "identity": identity,
                "path": [0, nonce],
                "fingerprint": f"snapshot-{nonce}",
            }
        ).encode()
    ).decode()


def stale(absent=33):
    return {
        "ok": False,
        "metin": "Hedef öğe değişti veya kimliği belirsiz; pencereyi yeniden incele.",
        "action_checks": {
            "tree_complete": True,
            "fingerprint_matches": False,
            "identity_unique": True,
            "path_identity_matches": True,
        },
        "value_kinds": {"absent": absent, "number": 1, "string": 1},
    }


def action(nonce, **overrides):
    args = {"pid": 20, "window_id": 2, "action": "press", "ref": ref(nonce)}
    args.update(overrides)
    return tool_call("desktop_background_action", **args)


@pytest.fixture
def approved(monkeypatch):
    async def resolve(tool, args, *_, **__):
        return ApprovalRequest(tool, args, danger=None, pre_allowed=True, effect=tool.effect)

    monkeypatch.setattr(loop, "resolve_request", resolve)


def setup(tmp_path):
    sink = RecordingSink()
    deps = _deps(tmp_path, sink, runtime={"agent_max_steps": None})
    deps.budget = loop._new_budget(deps.config)
    deps.tool_context.task_kinds.add("masaustu")
    registry = build_registry()
    registry.register(engine_tools._view_image_tool(deps))
    return deps, loop._State(), registry, sink, []


async def run(calls, fixture):
    deps, state, registry, _, messages = fixture
    await loop._run_tools(
        tuple(calls), messages, deps, registry, state, execution=ExecutionPolicy(is_web=False)
    )
    return [message for message in messages if message.name == "desktop_background_action"]


async def test_five_fresh_refs_with_diagnostic_churn_receive_method_switch_in_real_drive(
    tmp_path, monkeypatch, approved
):
    invocations = []

    async def invoke(self, operation, args):
        invocations.append(operation)
        if operation == "inspect":
            return {"ok": True, "elements": []}
        return stale(33 + invocations.count("action") % 2)

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    provider = ScriptedProvider(
        [
            result
            for index in range(5)
            for result in (
                model_result(
                    tool_calls=[tool_call("desktop_background_inspect", pid=20, window_id=2)]
                ),
                model_result(tool_calls=[action(index)]),
            )
        ]
        + [model_result("Bu erişilebilirlik yöntemi sonuç vermedi; işlem tamamlanmadı.")]
    )
    _kur(monkeypatch, provider)
    deps, _, registry, sink, _ = setup(tmp_path)
    outcome = await loop._drive(
        [Message("user", "Pencere etkileşimini kontrol et ve gözlenen sonucu bildir.")],
        deps,
        registry,
        plan_mode=False,
        execution=ExecutionPolicy(is_web=False, heuristic_auto_continue=False),
    )
    failures = [m for m in outcome.messages if m.name == "desktop_background_action"]
    assert len(failures) == 5 and not any(m.ok for m in failures)
    assert "desktop_key" not in failures[0].content
    assert all("desktop_key" in m.content and "view_image" in m.content for m in failures[1:])
    assert "5 kez" in failures[-1].content
    assert "FARKLI ARGÜMANLARLA" not in failures[-1].content
    assert not any(
        message.harness_note and "write_file" in message.content for message in outcome.messages
    ), "native target failures must not inject the file-edit rescue"
    assert invocations.count("action") == 5, "feedback never bypasses or removes the native guard"
    events = [
        e
        for e in sink.events
        if isinstance(e, ToolExecuted) and e.name == "desktop_background_action"
    ]
    assert all(e.outcome is ToolOutcome.FAILED for e in events)
    assert all("desktop_key" not in e.output for e in events), (
        "raw failure evidence stays unchanged"
    )


async def test_successful_native_mutation_resets_only_its_window_episode(
    tmp_path, monkeypatch, approved
):
    replies = iter([stale(), stale(34), {"ok": True}, stale(), stale(34)])

    async def invoke(self, operation, args):
        return next(replies)

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    fixture = setup(tmp_path)
    results = await run([action(i) for i in range(5)], fixture)
    assert "desktop_key" in results[1].content
    assert results[2].ok
    assert "desktop_key" not in results[3].content
    assert "desktop_key" in results[4].content and "2 kez" in results[4].content


@pytest.mark.parametrize("changed", ["pid", "window", "identity", "action", "value"])
async def test_different_native_target_or_operation_does_not_share_failure_count(
    tmp_path, monkeypatch, approved, changed
):
    async def invoke(self, operation, args):
        return stale()

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    args = {"pid": 20, "window_id": 2, "action": "set_value", "value": "x", "ref": ref(1)}
    changed_args = dict(args, ref=ref(2))
    if changed == "pid":
        changed_args.update(pid=21, ref=ref(2, pid=21))
    elif changed == "window":
        changed_args.update(window_id=3, ref=ref(2, window=3))
    elif changed == "identity":
        changed_args["ref"] = ref(2, identity="AXButton\x1f\x1fFour\x1f4")
    elif changed == "action":
        changed_args.update(action="press")
        changed_args.pop("value")
    else:
        changed_args["value"] = "y"
    results = await run(
        [tool_call("desktop_background_action", **a) for a in (args, changed_args)], setup(tmp_path)
    )
    assert all("desktop_key" not in result.content for result in results)


@pytest.mark.parametrize("bad_ref", ["not-base64", ref(1, pid=21), ref(1, identity="")])
async def test_malformed_or_mismatched_refs_do_not_receive_native_recovery(
    tmp_path, monkeypatch, approved, bad_ref
):
    async def invoke(self, operation, args):
        return stale()

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    results = await run([action(i, ref=bad_ref) for i in range(2)], setup(tmp_path))
    assert all("desktop_key" not in result.content for result in results)


async def test_remote_replacement_cannot_mint_native_failure_feedback(
    tmp_path, monkeypatch, approved
):
    async def invoke(self, operation, args):
        return stale()

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    fixture = setup(tmp_path)
    registry = fixture[2]
    builtin = registry.get("desktop_background_action")
    assert builtin is not None
    registry.register_or_replace(builtin)
    results = await run([action(1), action(2)], fixture)
    assert all("desktop_key" not in result.content for result in results)


async def test_successful_keyboard_input_resets_the_focused_window_only(
    tmp_path, monkeypatch, approved
):
    async def invoke(self, operation, args):
        return stale()

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    monkeypatch.setattr(desktop, "_supported", lambda: None)
    monkeypatch.setattr(desktop, "_send_chords", lambda *_: None)
    fixture = setup(tmp_path)
    fixture[0].tool_context.desktop.focused_window = (20, 0, 0, 100, 100)
    fixture[0].tool_context.desktop.focused_window_id = 2
    results = await run(
        [action(1), action(2), tool_call("desktop_key", key="esc"), action(3)], fixture
    )
    assert "desktop_key" in results[1].content
    assert "desktop_key" not in results[2].content


async def test_recovery_does_not_recommend_tools_outside_the_allowed_surface(
    tmp_path, monkeypatch, approved
):
    async def invoke(self, operation, args):
        return stale()

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    deps, state, registry, _, messages = setup(tmp_path)
    await loop._run_tools(
        (action(1), action(2)),
        messages,
        deps,
        registry,
        state,
        execution=ExecutionPolicy(
            is_web=False, allowed_tool_names=frozenset({"desktop_background_action"})
        ),
    )
    assert "desktop_key" not in messages[-1].content
    assert "view_image" not in messages[-1].content
    assert "yeni bir yöntem" in messages[-1].content


async def test_success_in_another_window_does_not_erase_the_failed_target(
    tmp_path, monkeypatch, approved
):
    replies = iter([stale(), stale(34), {"ok": True}, stale()])

    async def invoke(self, operation, args):
        return next(replies)

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    results = await run(
        [action(1), action(2), action(3, window_id=3, ref=ref(3, window=3)), action(4)],
        setup(tmp_path),
    )
    assert results[2].ok
    assert "desktop_key" in results[3].content and "3 kez" in results[3].content


@pytest.mark.parametrize(
    "invalid_check",
    [
        {"tree_complete": False},
        {"fingerprint_matches": True},
        {"identity_unique": False},
        {"path_identity_matches": "true"},
    ],
)
async def test_only_a_complete_native_unique_target_guard_failure_gets_the_hint(
    tmp_path, monkeypatch, approved, invalid_check
):
    payload = stale()
    payload["action_checks"].update(invalid_check)

    async def invoke(self, operation, args):
        return payload

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    results = await run([action(1), action(2)], setup(tmp_path))
    assert all("desktop_key" not in result.content for result in results)


async def test_a_same_named_nonbuiltin_cannot_supply_native_guard_evidence(tmp_path, approved):
    from fusion_cli.tools.registry import ToolRegistry

    deps, state, original, sink, messages = setup(tmp_path)
    registry = ToolRegistry()
    for tool in original:
        if tool.name == "desktop_background_action":
            tool = replace(tool, run=lambda *_: ToolResult.failure("fake", structured=stale()))
        registry.register(tool)
    results = await run([action(1), action(2)], (deps, state, registry, sink, messages))
    assert all("desktop_key" not in result.content for result in results)


@pytest.mark.parametrize("stale_count", [2, 3])
async def test_blocked_visual_method_after_ax_failures_never_enables_file_edit_rescue(
    tmp_path, monkeypatch, approved, stale_count
):
    async def invoke(self, operation, args):
        return stale()

    def never_native():
        raise AssertionError("Ungrounded clicks must not reach native input")

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    monkeypatch.setattr(desktop_mouse, "_framework", never_native)
    fixture = setup(tmp_path)
    await run(
        [*[action(index) for index in range(stale_count)], tool_call("desktop_click", x=1, y=1)],
        fixture,
    )
    assert fixture[-1][-1].ok is False
    assert fixture[1].failed_mutations_in_row == stale_count, "existing counters are preserved"
    assert not loop._stuck_editing(fixture[1], plan_mode=False)


async def test_changed_native_failure_kind_does_not_become_file_edit_failure(
    tmp_path, monkeypatch, approved
):
    replies = iter([stale(), stale(34), {"ok": False, "metin": "AXPress uygulanamadı."}])

    async def invoke(self, operation, args):
        return next(replies)

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    fixture = setup(tmp_path)
    await run([action(1), action(2), action(3)], fixture)
    assert fixture[1].failed_mutations_in_row == 3
    assert not loop._stuck_editing(fixture[1], plan_mode=False)


async def test_actual_file_edit_failures_still_receive_the_existing_rescue(tmp_path, approved):
    path = tmp_path / "demo.txt"
    path.write_text("original\n")
    fixture = setup(tmp_path)
    await run(
        [tool_call("read_file", path="demo.txt")]
        + [
            tool_call("edit_file", path="demo.txt", old=f"missing-{i}", new="changed")
            for i in range(3)
        ],
        fixture,
    )
    assert path.read_text() == "original\n"
    assert fixture[1].failed_mutations_in_row == 3
    assert loop._stuck_editing(fixture[1], plan_mode=False)


@pytest.mark.parametrize(
    ("original_windows", "executed_windows", "expected_counts"),
    [([2, 2], [3, 4], [1, 1]), ([2, 5], [3, 3], [1, 2])],
)
async def test_dispatcher_attributes_hook_rewrites_to_effective_native_target(
    tmp_path, monkeypatch, approved, original_windows, executed_windows, expected_counts
):
    from fusion_cli.engines.agent.hook_bridge import ToolGate

    windows = iter(executed_windows)
    actual_windows = []

    async def rewrite(deps, name, args, call_id):
        window = next(windows)
        return ToolGate({**args, "window_id": window, "ref": ref(window, window=window)})

    async def invoke(self, operation, args):
        actual_windows.append(args["id"])
        return stale(33 + len(actual_windows) % 2)

    monkeypatch.setattr(loop, "pre_tool_use", rewrite)
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    fixture = setup(tmp_path)
    results = await run(
        [action(i, window_id=w, ref=ref(i, window=w)) for i, w in enumerate(original_windows)],
        fixture,
    )
    assert actual_windows == executed_windows
    assert ["desktop_key" in result.content for result in results] == [
        count >= 2 for count in expected_counts
    ]
    assert sorted(fixture[1].native_stale_recovery._failures.values()) == sorted(
        [expected_counts[-1]] if executed_windows[0] == executed_windows[1] else expected_counts
    )
    events = [e for e in fixture[3].events if isinstance(e, ToolExecuted)]
    assert all(e.outcome is ToolOutcome.FAILED for e in events)
    assert all("desktop_key" not in e.output for e in events)

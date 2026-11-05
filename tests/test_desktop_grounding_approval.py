"""Unusable coordinate requests must not reach an approval dialog."""

from __future__ import annotations

import pytest

from fusion_cli.core.tool_content import ToolContent
from fusion_cli.core.tools import Tool, ToolEffect, ToolResult
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import desktop_grounding, loop
from fusion_cli.engines.agent.approval import ApprovalRequest, Decision
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.hook_bridge import ToolGate

from .fakes import ScriptedProvider, model_result, tool_call
from .test_desktop_visual_grounding import _actor, _capture, _helper_message, _setup


def _approval_boundary(monkeypatch, deps, events, *, decide=None):
    # Request resolution normally probes the native target. Keep the agent
    # dispatch/grounding real and replace that external boundary only.
    async def resolve(tool, args, *_, **__):
        events.append("resolve")
        return ApprovalRequest(tool, args, danger="synthetic risky target", effect=tool.effect)

    async def review(request, _deps):
        events.append("review")
        return request

    class Policy:
        async def decide(self, request):
            events.append("ask")
            return decide(request) if decide is not None else Decision.ALLOW

    monkeypatch.setattr(loop, "resolve_request", resolve)
    monkeypatch.setattr(loop, "review_auto_request", review)
    deps.policy = Policy()


def _click(registry, posted):
    registry.register(
        Tool(
            "desktop_click",
            "",
            {"type": "object"},
            lambda args, _ctx: posted.append(args) or ToolResult("posted"),
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )


@pytest.mark.parametrize("flow", ["missing", "unseen", "same-batch", "helper-same-batch"])
async def test_real_drive_never_asks_for_an_unconsumed_coordinate_observation(
    tmp_path, monkeypatch, flow
):
    deps, _state, registry, posted = _setup(tmp_path)
    events = []
    _approval_boundary(monkeypatch, deps, events)
    _click(registry, posted)

    def screen(_args, context):
        _capture_record, uri = _capture(deps)
        return ToolResult(
            "current screen", content=(ToolContent.image("image/png", uri.split(",")[1]),)
        )

    def helper(_args, context):
        return ToolResult("button at 10,10", visual_observation=context.desktop.current_capture)

    registry.register(Tool("desktop_screenshot", "", {"type": "object"}, screen))
    registry.register(Tool("view_image", "", {"type": "object"}, helper))
    click = tool_call("desktop_click", x=10, y=10)
    screen_call = tool_call("desktop_screenshot")
    results = []
    if flow == "missing":
        results.append(model_result(tool_calls=(click,)))
    elif flow == "same-batch":
        results.append(model_result(tool_calls=(screen_call, click)))
    else:
        results.append(model_result(tool_calls=(screen_call,)))
        calls = (
            (tool_call("view_image", path="screen.png"), click)
            if flow == "helper-same-batch"
            else (click,)
        )
        results.append(model_result(tool_calls=calls))
    results.append(model_result("Coordinate action was not executed."))
    provider = ScriptedProvider(results)
    monkeypatch.setattr(loop, "build_provider", lambda *_, **__: provider)
    messages = [Message("user", "Use the visible calculator button.")]
    await loop._drive(
        messages,
        deps,
        registry,
        plan_mode=False,
        execution=ExecutionPolicy(is_web=False),
    )
    assert not events, "an already unusable request must never reach native preview/review/ask"
    assert not posted
    assert any(message.name == "desktop_click" and message.ok is False for message in messages)


async def test_valid_receipt_reads_content_only_after_approval_and_still_dispatches(
    tmp_path, monkeypatch
):
    deps, state, registry, posted = _setup(tmp_path)
    capture, _ = _capture(deps)
    await _actor(monkeypatch, deps, state, [_helper_message(deps, state, capture)])
    events = []
    _approval_boundary(monkeypatch, deps, events)
    original = desktop_grounding.capture_file_matches

    def checked_file(*args):
        events.append("read")
        return original(*args)

    monkeypatch.setattr(desktop_grounding, "capture_file_matches", checked_file)
    _click(registry, posted)
    result, outcome = await loop._execute(
        tool_call("desktop_click", x=10, y=10),
        {"x": 10, "y": 10},
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    assert result.ok and outcome is loop.ToolOutcome.OK and posted == [{"x": 10, "y": 10}]
    assert events == ["resolve", "review", "ask", "read"]


async def test_denied_valid_receipt_never_reads_image_content(tmp_path, monkeypatch):
    deps, state, registry, posted = _setup(tmp_path)
    capture, _ = _capture(deps)
    await _actor(monkeypatch, deps, state, [_helper_message(deps, state, capture)])
    events = []
    _approval_boundary(monkeypatch, deps, events, decide=lambda _: Decision.DENIED)

    def forbidden_read(*_):
        raise AssertionError("image content was read before authorization")

    monkeypatch.setattr(desktop_grounding, "capture_file_matches", forbidden_read)
    _click(registry, posted)
    result, outcome = await loop._execute(
        tool_call("desktop_click", x=10, y=10),
        {"x": 10, "y": 10},
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    assert not result.ok and outcome is loop.ToolOutcome.DENIED and not posted
    assert events == ["resolve", "review", "ask"]


async def test_hook_coordinate_rewrite_is_checked_before_approval(tmp_path, monkeypatch):
    deps, state, registry, posted = _setup(tmp_path)
    capture, _ = _capture(deps, bounds=(10, 10, 20, 20))
    await _actor(monkeypatch, deps, state, [_helper_message(deps, state, capture)])
    events = []
    _approval_boundary(monkeypatch, deps, events)

    async def rewrite(*_):
        return ToolGate({"x": 90, "y": 90})

    monkeypatch.setattr(loop, "pre_tool_use", rewrite)
    _click(registry, posted)
    result, _ = await loop._execute(
        tool_call("desktop_click", x=15, y=15),
        {"x": 15, "y": 15},
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    assert not result.ok and not events and not posted


@pytest.mark.parametrize("change", ["capture", "focus", "updated-input", "content"])
async def test_final_guard_still_rejects_changes_during_approval(tmp_path, monkeypatch, change):
    from fusion_cli.engines.agent.approval import Allowance

    deps, state, registry, posted = _setup(tmp_path)
    capture, _ = _capture(deps)
    await _actor(monkeypatch, deps, state, [_helper_message(deps, state, capture)])
    events = []

    def decide(_request):
        if change == "capture":
            _capture(deps, name="new.png")
        elif change == "focus":
            deps.tool_context.desktop.invalidate_capture()
        elif change == "content":
            capture.path.write_bytes(b"changed after approval started")
        else:
            return Allowance({"x": 900, "y": 900})
        return Decision.ALLOW

    _approval_boundary(monkeypatch, deps, events, decide=decide)
    _click(registry, posted)
    result, _ = await loop._execute(
        tool_call("desktop_click", x=10, y=10),
        {"x": 10, "y": 10},
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    assert events[:3] == ["resolve", "review", "ask"]
    assert not result.ok and not posted


@pytest.mark.parametrize("matching_owner", [True, False])
async def test_owned_mouse_up_keeps_cleanup_exemption_without_licensing_a_foreign_release(
    tmp_path, monkeypatch, matching_owner
):
    from fusion_cli.tools import desktop_mouse

    deps, state, registry, _ = _setup(tmp_path)
    scope = desktop_grounding.owner(
        deps.tool_context,
        deps.conversation_id if matching_owner else "another-conversation",
        deps.attempt_id,
    )
    # Model a held native resource; the external platform release is the only
    # mocked boundary, and no real pointer event is posted by this fixture.
    state.desktop_grounding.held[0] = desktop_grounding.HeldMouse(
        0, (10, 10), scope, deps.tool_context
    )
    released = []

    def release(button, token, _context):
        released.append((button, token))
        return ToolResult("released")

    monkeypatch.setattr(desktop_mouse, "release_owned_mouse", release)
    events = []
    _approval_boundary(monkeypatch, deps, events)

    def never_use_model_coordinates(*_):
        raise AssertionError("owned cleanup cannot use the ordinary coordinate executor")

    registry.register(
        Tool(
            "desktop_mouse",
            "",
            {"type": "object"},
            never_use_model_coordinates,
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )
    args = {"action": "up", "button": "left", "x": 99999, "y": 88888}
    result, _ = await loop._execute(
        tool_call("desktop_mouse", **args),
        args,
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    if matching_owner:
        assert result.ok and released == [(0, state.desktop_grounding.token)]
        assert not state.desktop_grounding.held
        assert events == ["resolve", "review", "ask"]
    else:
        assert not result.ok and not released and not events
        assert 0 in state.desktop_grounding.held

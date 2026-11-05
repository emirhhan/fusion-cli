"""Actor screen actions require an observation delivered in a later request."""

from __future__ import annotations

# These helpers write only a tiny owned image; no screen/provider APIs are used.
import base64
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.core.desktop_frame import DesktopFrame
from fusion_cli.core.tool_content import ToolContent
from fusion_cli.core.tools import Tool, ToolEffect, ToolResult
from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent import engine_tools, loop
from fusion_cli.engines.agent.approval import ApprovalRequest
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.tools import desktop_mouse
from fusion_cli.tools.registry import ToolRegistry

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .image_fixture import image_bytes
from .test_agent_loop import _deps
from .test_desktop_screen import _png, _retina


@pytest.fixture
def approved(monkeypatch):
    async def resolve(tool, args, *_, **__):
        return ApprovalRequest(tool, args, danger=None, pre_allowed=True, effect=tool.effect)

    monkeypatch.setattr(loop, "resolve_request", resolve)


def _setup(tmp_path):
    deps = _deps(tmp_path, RecordingSink(), agent=ModelSpec("agent", "test/text", tags=("strict",)))
    deps.budget = loop._new_budget(deps.config)
    return deps, loop._State(), ToolRegistry(), []


async def test_capture_and_click_same_batch_cannot_use_undelivered_image(tmp_path, approved):
    deps, state, registry, posted = _setup(tmp_path)

    def capture(args, context):
        context.desktop.frame = DesktopFrame(100, 100, 0, 0, 100, 100)
        return ToolResult("screen.png", content=(ToolContent.image("image/png", "aGVsbG8="),))

    def click(args, context):
        posted.append(args)
        return ToolResult("sent")

    registry.register(Tool("desktop_screenshot", "", {"type": "object"}, capture))
    registry.register(
        Tool(
            "desktop_click",
            "",
            {"type": "object"},
            click,
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )
    messages = []
    await loop._run_tools(
        (tool_call("desktop_screenshot"), tool_call("desktop_click", x=10, y=10)),
        messages,
        deps,
        registry,
        state,
        execution=ExecutionPolicy(is_web=False),
    )
    assert not posted, "capture is not an actor observation until a later request consumes it"
    assert not messages[-1].ok


async def test_view_image_reexecutes_after_same_path_is_overwritten(tmp_path, monkeypatch):
    deps, state, registry, _ = _setup(tmp_path)
    path = tmp_path / "screen.png"
    executed = []

    def view(args, context):
        executed.append(path.read_text())
        return ToolResult(executed[-1])

    registry.register(Tool("view_image", "", {"type": "object"}, view))
    messages = []
    for value in ("one", "two", "three"):
        path.write_text(value)
        await loop._run_tools(
            (tool_call("view_image", path=str(path)),),
            messages,
            deps,
            registry,
            state,
            execution=ExecutionPolicy(is_web=False),
        )
    assert executed == ["one", "two", "three"]
    assert messages[-1].content == "three"


def _capture(deps, *, bounds=(0, 0, 100, 100), name="screen.png", data=None):
    data = image_bytes("PNG") if data is None else data
    path = deps.tool_context.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    view = deps.tool_context.desktop
    view.frame = DesktopFrame(100, 100, 0, 0, 100, 100)
    uri = "data:image/png;base64," + base64.b64encode(data).decode()
    capture = view.record_capture(path, uri, data, bounds)
    return capture, uri


@pytest.mark.parametrize("change", ["focus", "generation"])
def test_screenshot_does_not_rebind_capture_after_focus_or_generation_changes(
    tmp_path, monkeypatch, change
):
    from fusion_cli.tools import desktop_screen

    _retina(monkeypatch)
    deps, _state, _, _ = _setup(tmp_path)
    view = deps.tool_context.desktop
    view.focused_window = (1, 0, 0, 100, 100)
    view.focused_window_id = 11
    view.focused_window_title = "A"

    def captured_old_focus(*_, **__):
        if change == "focus":
            view.focused_window = (2, 0, 0, 100, 100)
            view.focused_window_id = 22
            view.focused_window_title = "B"
        else:
            _capture(deps, name="newer.png")
        return _png(100, 100)

    monkeypatch.setattr(desktop_screen, "_native_capture", captured_old_focus)
    result = desktop_screen.desktop_screenshot({"path": "old.png"}, deps.tool_context)
    assert not result.ok and not result.images
    assert view.current_capture is None or view.current_capture.path.name != "old.png"


@pytest.mark.parametrize("action", ["aba", "same", "failed"])
def test_actual_focus_invalidation_revokes_inflight_capture_even_when_identity_returns(
    tmp_path, monkeypatch, action
):
    from fusion_cli.engines.agent.desktop_grounding import current_capture
    from fusion_cli.tools import desktop_inspect, desktop_screen

    _retina(monkeypatch)
    deps, _state, _, _ = _setup(tmp_path)
    context = deps.tool_context
    title = ["A"]

    def focus_run(_script, app, _window):
        if app == "failed":
            return ToolResult.failure("synthetic focus failure")
        title[0] = app
        return ToolResult(f"{app}\t42\t{app}\t0\t0\t100\t100")

    monkeypatch.setattr(desktop_inspect, "_run", focus_run)
    monkeypatch.setattr(desktop_inspect, "_settled_foreground", lambda target, checks: target)
    monkeypatch.setattr(
        desktop_inspect,
        "invoke_sync",
        lambda *_args, **_kwargs: {
            "ok": True,
            "pid": 42,
            "window": {
                "id": 101 if title[0] == "A" else 102,
                "title": title[0],
                "bounds": [0.0, 0.0, 100.0, 100.0],
            },
        },
    )
    assert desktop_inspect.desktop_window_focus({"app": "A"}, context).ok

    def capture_old_pixels(*_args, **_kwargs):
        if action == "aba":
            assert desktop_inspect.desktop_window_focus({"app": "B"}, context).ok
        if action == "failed":
            assert not desktop_inspect.desktop_window_focus({"app": "failed"}, context).ok
            # Restoring A must not resurrect the pre-failure capture either.
        assert desktop_inspect.desktop_window_focus({"app": "A"}, context).ok
        return _png(100, 100)

    monkeypatch.setattr(desktop_screen, "_native_capture", capture_old_pixels)
    result = desktop_screen.desktop_screenshot({"path": "old-focus.png"}, context)
    assert not result.ok and not result.images and current_capture(context) is None


async def _actor(monkeypatch, deps, state, messages, *, result=None, masked=None):
    if result is None:
        result = replace(
            model_result("Observation consumed; choose the next action."),
            model=deps.config.agent.model,
        )
    provider = ScriptedProvider([result])
    monkeypatch.setattr(loop, "build_provider", lambda *_, **__: provider)

    async def consume(fn, *_):
        await fn()

    monkeypatch.setattr(loop, "_consume_with_liveness", consume)
    if masked is not None:
        monkeypatch.setattr(
            loop, "_masked_view", lambda *_, **__: SimpleNamespace(messages=masked, masked=0)
        )
    await loop._call_model(
        messages,
        deps,
        ToolRegistry(),
        state=state,
        execution=ExecutionPolicy(is_web=False),
        offer_tools=False,
    )
    return provider


def _helper_message(deps, state, capture, text="Visible button at 10,10", call_id="helper-1"):
    message = Message("tool", text, tool_call_id=call_id, name="view_image", ok=True)
    state.desktop_grounding.note_helper(
        capture, message, deps.tool_context, deps.conversation_id, deps.attempt_id
    )
    return message


def _preflight(deps, state, name="desktop_click", **args):
    return state.desktop_grounding.preflight(
        name, args or {"x": 10, "y": 10}, deps.tool_context, deps.conversation_id, deps.attempt_id
    )


async def test_helper_output_needs_later_actual_actor_request(tmp_path, monkeypatch):
    deps, state, _, _ = _setup(tmp_path)
    capture, _ = _capture(deps)
    message = _helper_message(deps, state, capture)
    assert _preflight(deps, state) is not None
    await _actor(monkeypatch, deps, state, [message])
    assert _preflight(deps, state) is None
    assert deps.config.agent.strict


async def test_close_during_authorized_content_check_revokes_lease(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import desktop_grounding

    deps, state, _, _ = _setup(tmp_path)
    capture, _ = _capture(deps)
    await _actor(monkeypatch, deps, state, [_helper_message(deps, state, capture)])

    def close_during_read(*_):
        state.desktop_grounding.close()
        return True

    monkeypatch.setattr(desktop_grounding, "capture_file_matches", close_during_read)
    assert _preflight(deps, state) is not None


async def test_coordinate_conversion_uses_immutable_acknowledged_geometry(tmp_path, monkeypatch):
    deps, state, _, _ = _setup(tmp_path)
    capture, _ = _capture(deps)
    await _actor(monkeypatch, deps, state, [_helper_message(deps, state, capture)])
    invocation = state.desktop_grounding.mouse_context(
        deps.tool_context, deps.conversation_id, deps.attempt_id
    )
    deps.tool_context.desktop.frame = DesktopFrame(100, 100, 900, 900, 200, 200)
    assert desktop_mouse._to_point(invocation, (10, 10)) == (10, 10)
    assert invocation.desktop_mouse_guard("desktop_mouse", {"x": 10, "y": 10}) is not None


@pytest.mark.parametrize("vision", [False, True])
async def test_direct_actor_image_requires_served_leaf_vision_capability(
    tmp_path, monkeypatch, vision
):
    deps, state, _, _ = _setup(tmp_path)
    if vision:
        deps.config = replace(
            deps.config, agent=replace(deps.config.agent, tags=("strict", "vision"))
        )
    _, uri = _capture(deps)
    await _actor(
        monkeypatch,
        deps,
        state,
        [Message("tool", "screen", name="desktop_screenshot", images=(uri,))],
    )
    assert (_preflight(deps, state) is None) is vision


async def test_vision_primary_does_not_grant_nonvision_fallback_result(tmp_path, monkeypatch):
    deps, state, _, _ = _setup(tmp_path)
    deps.config = replace(deps.config, agent=replace(deps.config.agent, tags=("strict", "vision")))
    _, uri = _capture(deps)
    result = replace(
        model_result("Fallback chose coordinates."), model="unconfigured/text-fallback"
    )
    await _actor(
        monkeypatch, deps, state, [Message("tool", "screen", images=(uri,))], result=result
    )
    assert _preflight(deps, state) is not None


@pytest.mark.parametrize(
    "case",
    [
        "masked",
        "wrong-call",
        "changed-text",
        "failed-actor",
        "cancelled",
        "different-drive",
        "different-scope",
        "different-capture",
        "changed-file",
    ],
)
async def test_stale_or_unconsumed_helper_never_authorizes_coordinates(tmp_path, monkeypatch, case):
    deps, state, _, _ = _setup(tmp_path)
    capture, _ = _capture(deps)
    message = _helper_message(deps, state, capture)
    actual = [message]
    result = None
    if case == "masked":
        actual = [replace(message, content="[output masked]")]
    elif case == "wrong-call":
        actual = [replace(message, tool_call_id="other")]
    elif case == "changed-text":
        actual = [replace(message, content="looked at some image")]
    elif case == "failed-actor":
        result = replace(model_result("failed"), ok=False)
    elif case == "cancelled":
        deps.tool_context.cancelled.set()
    await _actor(monkeypatch, deps, state, [message], result=result, masked=actual)
    if case == "different-drive":
        state = loop._State()
    elif case == "different-scope":
        deps.conversation_id = "another-chat"
    elif case == "different-capture":
        _capture(deps, data=image_bytes("PNG", (2, 2)))
    elif case == "changed-file":
        capture.path.write_bytes(b"changed after observation")
    assert _preflight(deps, state) is not None


async def test_crop_bounds_cover_both_drag_endpoints_and_coordinate_scroll(tmp_path, monkeypatch):
    deps, state, _, _ = _setup(tmp_path)
    capture, _ = _capture(deps, bounds=(10, 10, 20, 20))
    message = _helper_message(deps, state, capture)
    await _actor(monkeypatch, deps, state, [message])
    assert _preflight(deps, state, x=15, y=15) is None
    assert _preflight(deps, state, x=50, y=50) is not None
    assert (
        _preflight(deps, state, "desktop_mouse", action="drag", x=15, y=15, to_x=90, to_y=90)
        is not None
    )
    assert _preflight(deps, state, "desktop_scroll", x=90, y=90, lines=2) is not None
    assert _preflight(deps, state, "desktop_scroll", lines=2) is None
    assert _preflight(deps, state, "desktop_key", key="1 8 * 2 4") is None
    assert _preflight(deps, state, "desktop_background_action", action="press") is None


async def test_final_dispatch_rechecks_capture_after_permission_await(
    tmp_path, monkeypatch, approved
):
    deps, state, registry, posted = _setup(tmp_path)
    capture, _ = _capture(deps)
    message = _helper_message(deps, state, capture)
    await _actor(monkeypatch, deps, state, [message])

    class Policy:
        async def decide(self, request):
            _capture(deps, data=image_bytes("PNG", (2, 2)))
            from fusion_cli.engines.agent.approval import Decision

            return Decision.ALLOW

    deps.policy = Policy()
    registry.register(
        Tool(
            "desktop_click",
            "",
            {"type": "object"},
            lambda args, ctx: posted.append(args) or ToolResult("sent"),
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )
    result, _outcome = await loop._execute(
        tool_call("desktop_click", x=10, y=10),
        {"x": 10, "y": 10},
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    assert not posted and not result.ok


async def test_matching_immutable_helper_metadata_and_no_outside_root_read(tmp_path, monkeypatch):
    deps, _state, _, _ = _setup(tmp_path)
    deps.config = replace(deps.config, vision=ModelSpec("vision", "test/vision"))
    capture, uri = _capture(deps)
    seen = []

    async def describe(config, data, question):
        seen.append(data)
        return "visible_text: 0; description: calculator; uncertainty: none", None

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    tool = engine_tools._view_image_tool(deps)
    result = await tool.run({"path": str(capture.path)}, deps.tool_context)
    assert result.visual_observation is capture and seen == [uri]
    from fusion_cli.core.errors import PathAccessError

    with pytest.raises(PathAccessError):
        await tool.run({"path": str(tmp_path.parent / "outside.png")}, deps.tool_context)
    assert seen == [uri]


async def test_helper_cannot_bind_a_newer_capture_during_await(tmp_path, monkeypatch):
    deps, _state, _, _ = _setup(tmp_path)
    deps.config = replace(deps.config, vision=ModelSpec("vision", "test/vision"))
    capture, uri = _capture(deps)

    async def describe(config, data, question):
        assert data == uri
        _capture(deps, data=image_bytes("PNG", (2, 2)))
        return "old image observation", None

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    result = await engine_tools._view_image_tool(deps).run(
        {"path": str(capture.path)}, deps.tool_context
    )
    assert result.ok and result.visual_observation is None


async def test_helper_and_click_same_batch_still_cannot_use_new_helper_text(tmp_path, approved):
    deps, state, registry, posted = _setup(tmp_path)
    capture, _ = _capture(deps)
    registry.register(
        Tool(
            "view_image",
            "",
            {"type": "object"},
            lambda args, ctx: ToolResult("current visual observation", visual_observation=capture),
        )
    )
    registry.register(
        Tool(
            "desktop_click",
            "",
            {"type": "object"},
            lambda args, ctx: posted.append(args) or ToolResult("sent"),
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )
    messages = []
    await loop._run_tools(
        (tool_call("view_image", path=str(capture.path)), tool_call("desktop_click", x=10, y=10)),
        messages,
        deps,
        registry,
        state,
        execution=ExecutionPolicy(is_web=False),
    )
    assert not posted
    assert state.desktop_grounding.pending
    assert state.desktop_grounding.acknowledged is None


async def test_replaced_post_hook_output_cannot_become_trusted_observation(tmp_path, monkeypatch):
    deps, state, registry, _ = _setup(tmp_path)
    capture, _ = _capture(deps)
    registry.register(
        Tool(
            "view_image",
            "",
            {"type": "object"},
            lambda args, ctx: ToolResult("trusted visual observation", visual_observation=capture),
        )
    )

    async def hook(*_, **__):
        return loop.ToolNote(replaced_output="some replacement")

    monkeypatch.setattr(loop, "post_tool_use", hook)
    messages = []
    await loop._run_tools(
        (tool_call("view_image", path=str(capture.path)),),
        messages,
        deps,
        registry,
        state,
        execution=ExecutionPolicy(is_web=False),
    )
    assert not state.desktop_grounding.pending
    await _actor(monkeypatch, deps, state, messages)
    assert _preflight(deps, state) is not None


async def test_final_dispatch_rechecks_after_effect_recorder_await(tmp_path, monkeypatch, approved):
    deps, state, registry, posted = _setup(tmp_path)
    capture, _ = _capture(deps)
    message = _helper_message(deps, state, capture)
    await _actor(monkeypatch, deps, state, [message])

    class Recorder:
        async def prepare(self, *_):
            _capture(deps, data=image_bytes("PNG", (2, 2)))

        async def finish(self, *_):
            raise AssertionError("No effect dispatched")

    deps.effect_recorder = Recorder()
    registry.register(
        Tool(
            "desktop_click",
            "",
            {"type": "object"},
            lambda args, ctx: posted.append(args) or ToolResult("sent"),
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )
    result, _ = await loop._execute(
        tool_call("desktop_click", x=10, y=10),
        {"x": 10, "y": 10},
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    assert not result.ok and not posted


async def test_crop_without_full_frame_never_licenses_coordinates(tmp_path, monkeypatch):
    deps, state, _, _ = _setup(tmp_path)
    capture, uri = _capture(deps, bounds=(10, 10, 20, 20))
    deps.tool_context.desktop.frame = None
    capture = deps.tool_context.desktop.record_capture(
        capture.path, uri, capture.path.read_bytes(), (10, 10, 20, 20)
    )
    message = _helper_message(deps, state, capture)
    await _actor(monkeypatch, deps, state, [message])
    assert "tam desktop_screenshot" in _preflight(deps, state, x=15, y=15)


@pytest.mark.parametrize("observation,error", [("", None), ("ignored", "helper failed")])
async def test_failed_or_empty_helper_never_returns_frame_receipt(
    tmp_path, monkeypatch, observation, error
):
    deps, _state, _, _ = _setup(tmp_path)
    deps.config = replace(deps.config, vision=ModelSpec("vision", "test/vision"))
    capture, _ = _capture(deps)

    async def describe(*_):
        return observation, error

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    result = await engine_tools._view_image_tool(deps).run(
        {"path": str(capture.path)}, deps.tool_context
    )
    assert not result.ok and result.visual_observation is None


async def test_file_change_during_helper_await_has_no_frame_receipt(tmp_path, monkeypatch):
    deps, _state, _, _ = _setup(tmp_path)
    deps.config = replace(deps.config, vision=ModelSpec("vision", "test/vision"))
    capture, uri = _capture(deps)

    async def describe(_config, data, _question):
        assert data == uri
        capture.path.write_bytes(image_bytes("PNG", (2, 2)))
        return "observation of the old immutable image", None

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    result = await engine_tools._view_image_tool(deps).run(
        {"path": str(capture.path)}, deps.tool_context
    )
    assert result.visual_observation is None


async def test_denied_view_image_has_no_preapproval_content_read(tmp_path, monkeypatch, approved):
    deps, state, registry, _ = _setup(tmp_path)
    deps.config = replace(deps.config, vision=ModelSpec("vision", "test/vision"))

    def never_read(_):
        raise AssertionError("Denied image must not be opened for a cache key")

    monkeypatch.setattr(engine_tools, "load_image_data_uri", never_read)

    class Deny:
        async def decide(self, _):
            from fusion_cli.engines.agent.approval import Decision

            return Decision.DENIED

    deps.policy = Deny()
    registry.register(engine_tools._view_image_tool(deps))
    # Force an existing permission rule boundary without changing tool semantics.
    monkeypatch.setattr(loop, "_rule_gates", lambda *_: True)
    for _ in range(3):
        result, _outcome = await loop._execute(
            tool_call("view_image", path="screen.png"),
            {"path": "screen.png"},
            deps,
            registry,
            execution=ExecutionPolicy(is_web=False),
            state=state,
        )
        assert not result.ok

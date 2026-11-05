"""Owned mouse cleanup uses no model coordinate or new movement request."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fusion_cli.core.tools import ToolContext, ToolResult
from fusion_cli.tools import desktop_lock, desktop_mouse, desktop_win32

from .test_desktop_visual_grounding import _capture, _helper_message, _setup


@pytest.fixture(autouse=True)
def physical_boundary(monkeypatch):
    monkeypatch.setattr(desktop_mouse, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_mouse, "_framework", lambda: object())
    monkeypatch.setattr(desktop_mouse, "_trusted", lambda _: True)
    monkeypatch.setattr(desktop_lock, "claim", lambda **_: None)
    monkeypatch.setattr(desktop_mouse, "_PHYSICAL_BUTTON_OWNERS", {})
    monkeypatch.setattr(desktop_mouse, "_FAILED_RELEASES", {})
    monkeypatch.setattr(desktop_mouse, "_PENDING_RELEASES", {})
    monkeypatch.setattr(desktop_mouse, "_CLEANUP_WORKER_ACTIVE", False)
    cleanup_threads = []

    def cleanup_thread(*args, **kwargs):
        thread = threading.Thread(*args, **kwargs)
        cleanup_threads.append(thread)
        return thread

    monkeypatch.setattr(desktop_mouse, "Thread", cleanup_thread)

    def wait_for_cleanup():
        for thread in cleanup_threads:
            thread.join(3)
            assert not thread.is_alive(), "synthetic cleanup must terminate before fixture teardown"

    yield wait_for_cleanup
    wait_for_cleanup()


def grounded(tmp_path):
    deps, state, _, _ = _setup(tmp_path)
    capture, _ = _capture(deps)
    message = _helper_message(deps, state, capture)
    observation = state.desktop_grounding.for_request([message], deps.tool_context, "", "")
    state.desktop_grounding.acknowledge(
        observation,
        usable=True,
        images_supported=False,
        context=deps.tool_context,
        conversation_id="",
        attempt_id="",
    )
    return deps, state, state.desktop_grounding.mouse_context(deps.tool_context, "", "")


def test_close_returns_while_its_own_free_mutex_native_cleanup_is_hung(tmp_path, monkeypatch):
    _deps, state, context = grounded(tmp_path)
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda *_: None)
    assert desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context).ok
    entered, resume, returned = threading.Event(), threading.Event(), threading.Event()

    def cleanup(*_):
        entered.set()
        assert resume.wait(2)
        return ToolResult("released")

    monkeypatch.setattr(desktop_mouse, "_release_owned_mouse", cleanup)
    closer = threading.Thread(target=lambda: (state.desktop_grounding.close(), returned.set()))
    closer.start()
    try:
        assert entered.wait(1)
        assert returned.wait(0.15), "close must not execute native cleanup synchronously"
    finally:
        resume.set()
        closer.join(2)


@pytest.mark.parametrize("release_one", [False, True])
def test_each_owned_button_is_released_once_without_overwriting(
    tmp_path, monkeypatch, release_one, physical_boundary
):
    _deps, state, context = grounded(tmp_path)
    released = []
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda *_: None)
    monkeypatch.setattr(
        desktop_mouse,
        "_release_owned_mouse",
        lambda button, _: released.append(button) or ToolResult("released"),
    )
    for button in ("left", "right"):
        assert desktop_mouse.desktop_mouse(
            {"action": "down", "button": button, "x": 10, "y": 10}, context
        ).ok
    assert set(state.desktop_grounding.held) == {0, 1}
    if release_one:
        held = state.desktop_grounding.matching_release(
            "desktop_mouse", {"action": "up", "button": "left"}, context, "", ""
        )
        assert held is not None and state.desktop_grounding.release(held).ok
        assert set(state.desktop_grounding.held) == {1}
    state.desktop_grounding.close()
    state.desktop_grounding.close()
    physical_boundary()
    assert sorted(released) == [0, 1]
    assert not state.desktop_grounding.held and not desktop_mouse._PHYSICAL_BUTTON_OWNERS


def test_successful_second_button_cleanup_preserves_first_button_failure(
    tmp_path, monkeypatch, physical_boundary
):
    _deps, state, context = grounded(tmp_path)
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda *_: None)
    for button in ("left", "right"):
        assert desktop_mouse.desktop_mouse(
            {"action": "down", "button": button, "x": 10, "y": 10}, context
        ).ok
    monkeypatch.setattr(
        desktop_mouse,
        "_release_owned_mouse",
        lambda button, _: ToolResult.failure("left failed") if button == 0 else ToolResult("ok"),
    )
    state.desktop_grounding.close()
    physical_boundary()
    assert state.desktop_grounding.cleanup_error == "left failed"
    assert set(state.desktop_grounding.held) == {0}
    assert set(desktop_mouse._PHYSICAL_BUTTON_OWNERS) == {0}


def test_new_button_queued_during_failed_cleanup_is_not_lost_or_busy_retried(
    tmp_path, monkeypatch, physical_boundary
):
    _deps, state, context = grounded(tmp_path)
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda *_: None)
    for button in ("left", "right"):
        assert desktop_mouse.desktop_mouse(
            {"action": "down", "button": button, "x": 10, "y": 10}, context
        ).ok
    entered, resume = threading.Event(), threading.Event()
    attempts = []

    def release(button, _):
        attempts.append(button)
        if button == 0:
            entered.set()
            assert resume.wait(2)
            return ToolResult.failure("left remains held")
        return ToolResult("right released")

    original = desktop_mouse.request_owned_release

    def request(button, *args):
        original(button, *args)
        if button == 0:
            assert entered.wait(1)

    monkeypatch.setattr(desktop_mouse, "_release_owned_mouse", release)
    monkeypatch.setattr(desktop_mouse, "request_owned_release", request)
    try:
        state.desktop_grounding.close()
        assert attempts == [0]
    finally:
        resume.set()
        physical_boundary()
    assert attempts == [0, 1]
    assert set(state.desktop_grounding.held) == {0}
    assert state.desktop_grounding.cleanup_error == "left remains held"


def test_native_cleanup_uses_current_pointer_and_single_up(tmp_path, monkeypatch):
    context = ToolContext(root=tmp_path)
    token = object()
    desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] = token
    framework = SimpleNamespace(
        CGEventCreate=Mock(return_value=77),
        CGEventGetLocation=Mock(return_value=desktop_mouse._Point(345, 678)),
        CFRelease=Mock(),
    )
    monkeypatch.setattr(desktop_mouse, "_framework", lambda: framework)
    posted = []
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda _, plan: posted.extend(plan))
    result = desktop_mouse.release_owned_mouse(0, token, context)
    assert result.ok
    assert [(event.kind, event.x, event.y) for event in posted] == [(2, 345, 678)]
    framework.CGEventGetLocation.assert_called_once_with(77)
    framework.CFRelease.assert_called_once_with(77)


def test_cleanup_pointer_failure_emits_nothing(tmp_path, monkeypatch):
    token = object()
    desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] = token
    framework = SimpleNamespace(
        CGEventCreate=Mock(return_value=None), CGEventGetLocation=Mock(), CFRelease=Mock()
    )
    monkeypatch.setattr(desktop_mouse, "_framework", lambda: framework)
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda *_: pytest.fail("must not post"))
    assert not desktop_mouse.release_owned_mouse(0, token, ToolContext(root=tmp_path)).ok
    framework.CGEventGetLocation.assert_not_called()


def test_win_cleanup_has_up_without_move_or_virtual_screen(tmp_path, monkeypatch):
    token = object()
    desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] = token
    monkeypatch.setattr(desktop_win32, "active", lambda: True)
    sender = SimpleNamespace(
        send=Mock(), virtual_screen=Mock(side_effect=AssertionError("no MOVE"))
    )
    monkeypatch.setattr(desktop_win32, "api", lambda: sender)
    assert desktop_mouse.release_owned_mouse(0, token, ToolContext(root=tmp_path)).ok
    specs = sender.send.call_args.args[0]
    assert len(specs) == 1 and specs[0].flags == 0x4
    sender.virtual_screen.assert_not_called()


def test_old_owner_cleanup_cannot_release_new_actor_button(tmp_path, monkeypatch):
    old, new = object(), object()
    desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] = new
    monkeypatch.setattr(
        desktop_mouse, "_release_owned_mouse", lambda *_: pytest.fail("foreign ownership")
    )
    result = desktop_mouse.release_owned_mouse(0, old, ToolContext(root=tmp_path))
    assert result.ok and desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] is new


def test_close_queues_without_waiting_and_late_down_cleans_before_new_actor(tmp_path, monkeypatch):
    _deps_a, state_a, context_a = grounded(tmp_path / "a")
    _deps_b, state_b, context_b = grounded(tmp_path / "b")
    entered = threading.Event()
    resume = threading.Event()
    closed = threading.Event()
    order = []

    def post(_, plan):
        if any(event.kind == 1 for event in plan):
            if not entered.is_set():
                entered.set()
                assert resume.wait(3)
                order.append("A down")
            else:
                order.append("B down")

    monkeypatch.setattr(desktop_mouse, "_post_mouse", post)
    monkeypatch.setattr(
        desktop_mouse,
        "_release_owned_mouse",
        lambda button, ctx: order.append("owned up") or ToolResult("released"),
    )
    thread_a = threading.Thread(
        target=lambda: desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context_a)
    )
    thread_a.start()
    assert entered.wait(2)
    closer = threading.Thread(target=lambda: (state_a.desktop_grounding.close(), closed.set()))
    closer.start()
    assert closed.wait(1), "close must not wait on hung physical post"
    thread_b = threading.Thread(
        target=lambda: desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context_b)
    )
    thread_b.start()
    resume.set()
    thread_a.join(3)
    thread_b.join(3)
    closer.join(3)
    assert not thread_a.is_alive() and not thread_b.is_alive()
    assert order[:3] == ["A down", "owned up", "B down"]
    assert desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] is state_b.desktop_grounding.token
    state_b.desktop_grounding.close()


def test_cancelled_actor_waiting_on_other_post_exits_before_unlock(tmp_path, monkeypatch):
    _deps_a, state_a, context_a = grounded(tmp_path / "a")
    _deps_b, state_b, context_b = grounded(tmp_path / "b")
    entered = threading.Event()
    resume = threading.Event()
    b_done = threading.Event()
    posted = []

    def post(_, plan):
        posted.append(plan)
        entered.set()
        assert resume.wait(3)

    monkeypatch.setattr(desktop_mouse, "_post_mouse", post)
    monkeypatch.setattr(desktop_mouse, "_release_owned_mouse", lambda *_: ToolResult("released"))
    thread_a = threading.Thread(
        target=lambda: desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context_a)
    )
    thread_a.start()
    assert entered.wait(2)
    results = []

    def b():
        results.append(desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context_b))
        b_done.set()

    thread_b = threading.Thread(target=b)
    thread_b.start()
    context_b.cancelled.set()
    try:
        assert b_done.wait(1), "cancelled waiter cannot remain behind hung prior actor"
        assert not results[0].ok and len(posted) == 1
    finally:
        resume.set()
        thread_a.join(3)
        thread_b.join(3)
        state_a.desktop_grounding.close()
        state_b.desktop_grounding.close()


def test_unresolved_cleanup_blocks_new_down_without_overwriting_owner(
    tmp_path, monkeypatch, caplog, physical_boundary
):
    _deps_a, state_a, context_a = grounded(tmp_path / "a")
    posted = []
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda _, plan: posted.append(plan))
    assert desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context_a).ok
    reports = []
    state_a.desktop_grounding.failure_reporter = reports.append
    monkeypatch.setattr(
        desktop_mouse,
        "_release_owned_mouse",
        lambda *_: ToolResult.failure("native release failed"),
    )
    state_a.desktop_grounding.close()
    physical_boundary()
    assert state_a.desktop_grounding.cleanup_error == "native release failed"
    assert reports == ["native release failed"]
    assert "native release failed" in caplog.text
    _deps_b, state_b, context_b = grounded(tmp_path / "b")
    result = desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context_b)
    assert not result.ok and len(posted) == 1
    assert desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] is state_a.desktop_grounding.token
    monkeypatch.setattr(desktop_mouse, "_release_owned_mouse", lambda *_: ToolResult("released"))
    assert desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context_b).ok
    assert desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] is state_b.desktop_grounding.token
    assert not state_a.desktop_grounding.cleanup_error
    state_b.desktop_grounding.close()


@pytest.mark.parametrize("windows", [False, True])
def test_platform_post_failure_keeps_owned_button_and_records_failure(
    tmp_path, monkeypatch, windows
):
    token = object()
    desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] = token
    context = ToolContext(root=tmp_path)
    monkeypatch.setattr(desktop_win32, "active", lambda: windows)

    def failed(*_):
        raise OSError("release post unavailable")

    if windows:
        monkeypatch.setattr(desktop_win32, "api", lambda: SimpleNamespace(send=failed))
    else:
        framework = SimpleNamespace(
            CGEventCreate=Mock(return_value=1),
            CGEventGetLocation=Mock(return_value=desktop_mouse._Point(4, 5)),
            CFRelease=Mock(),
        )
        monkeypatch.setattr(desktop_mouse, "_framework", lambda: framework)
        monkeypatch.setattr(desktop_mouse, "_post_mouse", failed)
    result = desktop_mouse.release_owned_mouse(0, token, context)
    assert not result.ok
    assert desktop_mouse._PHYSICAL_BUTTON_OWNERS[0] is token
    assert desktop_mouse._FAILED_RELEASES[0] is token


def test_closed_actor_waiter_exits_before_other_actor_unblocks(tmp_path, monkeypatch):
    _deps_a, state_a, context_a = grounded(tmp_path / "a")
    _deps_b, state_b, context_b = grounded(tmp_path / "b")
    entered = threading.Event()
    resume = threading.Event()
    done = threading.Event()
    posted = []

    def post(_, plan):
        posted.append(plan)
        entered.set()
        assert resume.wait(3)

    monkeypatch.setattr(desktop_mouse, "_post_mouse", post)
    monkeypatch.setattr(desktop_mouse, "_release_owned_mouse", lambda *_: ToolResult("released"))
    a = threading.Thread(
        target=lambda: desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context_a)
    )
    a.start()
    assert entered.wait(2)
    results = []

    def waiting():
        results.append(desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context_b))
        done.set()

    b = threading.Thread(target=waiting)
    b.start()
    state_b.desktop_grounding.close()
    try:
        assert done.wait(1)
        assert not results[0].ok and len(posted) == 1
    finally:
        resume.set()
        a.join(3)
        b.join(3)
        state_a.desktop_grounding.close()


async def test_matching_model_up_after_frame_change_uses_no_model_coordinates(
    tmp_path, monkeypatch
):
    from fusion_cli.core.tools import Tool, ToolEffect
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.approval import ApprovalRequest
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.tools.registry import ToolRegistry

    from .fakes import tool_call

    deps, state, context = grounded(tmp_path)
    posted = []
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda _, plan: posted.append(plan))
    assert desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, context).ok
    posted.clear()
    _capture(deps, data=b"new captured bytes")
    framework = SimpleNamespace(
        CGEventCreate=Mock(return_value=1),
        CGEventGetLocation=Mock(return_value=desktop_mouse._Point(44, 55)),
        CFRelease=Mock(),
    )
    monkeypatch.setattr(desktop_mouse, "_framework", lambda: framework)

    async def approval(tool, args, *_, **__):
        return ApprovalRequest(tool, args, danger=None, pre_allowed=True, effect=tool.effect)

    monkeypatch.setattr(loop, "resolve_request", approval)
    registry = ToolRegistry()

    def forbidden(*_):
        pytest.fail("normal coordinate executor must not run")

    registry.register(
        Tool(
            "desktop_mouse",
            "",
            {"type": "object"},
            forbidden,
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )
    args = {"action": "up", "x": 99999, "y": 88888}
    result, _ = await loop._execute(
        tool_call("desktop_mouse", **args),
        args,
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    assert result.ok and not state.desktop_grounding.held
    assert [[(event.kind, event.x, event.y) for event in plan] for plan in posted] == [
        [(2, 44, 55)]
    ]


async def test_drive_cancellation_finally_cleans_only_its_owned_down(
    tmp_path, monkeypatch, physical_boundary
):
    import asyncio

    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.tools.registry import ToolRegistry

    deps, _unused, _context = grounded(tmp_path)
    started = asyncio.Event()
    released = []
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda *_: None)
    monkeypatch.setattr(
        desktop_mouse,
        "_release_owned_mouse",
        lambda button, context: released.append(button) or ToolResult("released"),
    )

    async def body(_messages, actor, _registry, *, state, **__):
        capture, _ = _capture(actor)
        message = _helper_message(actor, state, capture)
        observation = state.desktop_grounding.for_request([message], actor.tool_context, "", "")
        state.desktop_grounding.acknowledge(
            observation,
            usable=True,
            images_supported=False,
            context=actor.tool_context,
            conversation_id="",
            attempt_id="",
        )
        ctx = state.desktop_grounding.mouse_context(actor.tool_context, "", "")
        assert desktop_mouse.desktop_mouse({"action": "down", "x": 10, "y": 10}, ctx).ok
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(loop, "_drive_loop", body)
    task = asyncio.create_task(
        loop._drive(
            [], deps, ToolRegistry(), plan_mode=False, execution=ExecutionPolicy(is_web=False)
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    physical_boundary()
    assert released == [0] and not desktop_mouse._PHYSICAL_BUTTON_OWNERS

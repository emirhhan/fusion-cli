"""Gerçek Page işlemleri sahte Page ile; model/tarayıcı açılmaz."""

from __future__ import annotations

from pathlib import Path

from evals.kabul.areas.platform_observer import RouteStep, collect_trace
from evals.kabul.areas.platform_trace import TraceAction, TraceStatus, verify_trace


class Keys:
    def __init__(self, owner):
        self.owner = owner

    def down(self, key):
        self.owner.calls.append(("down", key))

    def up(self, key):
        self.owner.calls.append(("up", key))


class Page:
    def __init__(self, observations):
        self.observations = iter(observations)
        self.calls = []
        self.keyboard = Keys(self)

    def evaluate(self, script):
        assert "__GAME_STATE__" not in script
        assert "window." not in script
        assert "getBoundingClientRect" in script
        self.calls.append(("read",))
        return next(self.observations)

    def screenshot(self):
        self.calls.append(("frame",))
        return b"actual screenshot bytes from fake Page"

    def click(self, selector):
        self.calls.append(("click", selector))

    def wait_for_timeout(self, duration):
        self.calls.append(("wait", duration))


def observed(x=0, phase="playing"):
    return {
        "phase": phase,
        "level": 1,
        "player": [x, 0],
        "keys": ["key"],
        "keys_complete": True,
        "contact": False,
        "health": 3,
        "score": 0,
        "objects": [],
        "geometry": [["player", x, 0, 10, 10]],
    }


def test_actual_key_down_up_and_capture_are_used(tmp_path: Path):
    play = Page([observed(), observed(x=10)])
    idle = Page([observed(), observed()])
    result = collect_trace(
        play,
        idle,
        (RouteStep(TraceAction.MOVE, ("ArrowRight",), 250),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    assert ("down", "ArrowRight") in play.calls
    assert ("up", "ArrowRight") in play.calls
    assert ("down", "ArrowRight") not in idle.calls
    assert len(tuple((tmp_path / "frames").glob("*.png"))) == 4
    assert result.events[0].after.player == (10, 0)
    assert result.source_digest == "a" * 64
    assert not verify_trace(result.events).complete


def test_hook_only_or_missing_dom_never_produces_semantic_pass(tmp_path: Path):
    result = collect_trace(
        Page([None, None]),
        None,
        (RouteStep(TraceAction.START, (), 250, "button.start"),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    assert result.events == ()
    assert verify_trace(result.events).status is TraceStatus.UNVERIFIED
    assert result.unverified_steps == (0,)


def test_click_start_does_not_use_keyboard_fallback(tmp_path: Path):
    page = Page([observed(phase="menu"), observed()])
    result = collect_trace(
        page,
        None,
        (RouteStep(TraceAction.START, (), 250, "button.start"),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    assert ("click", "button.start") in page.calls
    assert not any(call[0] == "down" for call in page.calls)
    assert result.events[0].action is TraceAction.START


def test_unmatched_idle_baseline_does_not_prove_movement(tmp_path: Path):
    result = collect_trace(
        Page([observed(), observed(x=10)]),
        Page([observed(x=20), observed(x=20)]),
        (RouteStep(TraceAction.MOVE, ("ArrowRight",), 250),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    assert result.events[0].idle_after is None


def test_missing_route_adapter_returns_invalid_without_browser(tmp_path: Path, monkeypatch):
    from evals.kabul.areas import platform_game

    def forbidden(*args, **kwargs):
        raise AssertionError("Tarayıcı başlamamalı.")

    monkeypatch.setattr(platform_game, "open_page", forbidden)
    result = platform_game.inspect_platform(tmp_path, ())
    assert result.invalid_reason
    assert not result.all_passed


def test_adapter_exports_real_capture_but_incomplete_trace_is_not_pass(tmp_path: Path):
    import json

    from evals.kabul.areas.platform_game import inspect_pages

    result = inspect_pages(
        Page([observed(phase="menu"), observed()]),
        None,
        (RouteStep(TraceAction.START, (), 250, "button.start"),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    assert result.inspection.invalid_reason
    assert not result.trace.complete
    payload = json.loads((tmp_path / "frames/platform-observation.json").read_text())
    assert payload["quality_verified"] is False
    assert payload["capture"]["observations"][0]["frame_name"] == "step-0-before.png"


def test_pressed_key_is_released_when_wait_raises(tmp_path: Path):
    import pytest

    class FailingPage(Page):
        def wait_for_timeout(self, duration):
            raise RuntimeError("fake page crash")

    page = FailingPage([observed()])
    with pytest.raises(RuntimeError, match="fake page crash"):
        collect_trace(
            page,
            None,
            (RouteStep(TraceAction.MOVE, ("ArrowRight",), 250),),
            tmp_path / "frames",
            source_digest="a" * 64,
        )
    assert ("up", "ArrowRight") in page.calls


def test_reset_key_cannot_be_labelled_as_move():
    import pytest

    with pytest.raises(ValueError, match="eylem"):
        RouteStep(TraceAction.MOVE, ("r",), 250)


def test_pause_measures_world_after_press_then_wait(tmp_path: Path):
    page = Page([observed(), observed(phase="paused"), observed(phase="paused")])
    result = collect_trace(
        page,
        None,
        (RouteStep(TraceAction.PAUSE, ("p",), 250),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    criterion = next(item for item in verify_trace(result.events).criteria if item.name == "pause")
    assert criterion.status is TraceStatus.PASSED
    assert ("down", "p") in page.calls


def test_incomplete_key_visibility_does_not_prove_collection(tmp_path: Path):
    before = observed()
    before.update(keys=[], keys_complete=False, contact=True)
    after = observed()
    after.update(level=2)
    result = collect_trace(
        Page([before, after]),
        None,
        (RouteStep(TraceAction.DOOR, ("ArrowRight",), 250),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    assert result.events[0].before.remaining_keys is None
    criterion = next(
        item for item in verify_trace(result.events).criteria if item.name == "level_sequence"
    )
    assert criterion.status is TraceStatus.UNVERIFIED


def test_pause_press_level_skip_is_not_hidden_by_wait_snapshot(tmp_path: Path):
    paused = observed(phase="paused")
    paused["level"] = 3
    result = collect_trace(
        Page([observed(), paused, paused]),
        None,
        (RouteStep(TraceAction.PAUSE, ("p",), 250),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    assert verify_trace(result.events).status is TraceStatus.FAILED


def test_missing_pause_prepress_observation_stays_unverified(tmp_path: Path):
    paused = observed(phase="paused")
    result = collect_trace(
        Page([None, paused, paused]),
        None,
        (RouteStep(TraceAction.PAUSE, ("p",), 250),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    assert result.unverified_steps == (0,)
    assert result.events
    assert result.observations[0].snapshot is None


def test_adapter_keeps_missing_prepress_integrity_unknown(tmp_path: Path):
    from evals.kabul.areas.platform_game import inspect_pages

    paused = observed(phase="paused")
    result = inspect_pages(
        Page([None, paused, paused]),
        None,
        (RouteStep(TraceAction.PAUSE, ("p",), 250),),
        tmp_path / "frames",
        source_digest="a" * 64,
    )
    criterion = next(item for item in result.trace.criteria if item.name == "observer_integrity")
    assert criterion.status is TraceStatus.UNVERIFIED
    assert result.inspection.invalid_reason

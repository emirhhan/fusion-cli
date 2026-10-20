"""Platform görevine ait gerçek-input izi eksik veya sahte başarıyı geçirmez."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.kabul.areas.platform_trace import (
    PlatformPhase,
    PlatformSnapshot,
    TraceAction,
    TraceEvent,
    TraceStatus,
    verify_trace,
)


def snapshot(
    level=1,
    *,
    phase=PlatformPhase.PLAYING,
    x=0,
    y=0,
    keys=frozenset({"key"}),
    contact=False,
    hp=3,
    score=0,
    objects=frozenset(),
):
    return PlatformSnapshot(phase, level, (x, y), keys, contact, hp, score, objects, "a" * 64)


def event(action, before, after, idle=None):
    return TraceEvent(action, before, after, idle, ("b" * 64, "c" * 64))


def status(events, criterion):
    return next(
        item.status for item in verify_trace(tuple(events)).criteria if item.name == criterion
    )


def test_keyless_door_advances_is_failure():
    assert (
        status([event(TraceAction.DOOR, snapshot(contact=True), snapshot(2))], "locked_door")
        is TraceStatus.FAILED
    )


def test_level_one_to_three_skipping_is_failure():
    assert (
        status(
            [event(TraceAction.DOOR, snapshot(keys=frozenset(), contact=True), snapshot(3))],
            "level_sequence",
        )
        is TraceStatus.FAILED
    )


def test_hud_only_input_change_does_not_prove_movement():
    before = snapshot()
    assert (
        status([event(TraceAction.MOVE, before, replace(before, score=10), before)], "movement")
        is TraceStatus.FAILED
    )


def test_pause_keeps_phase_but_world_moves_is_failure():
    assert (
        status(
            [
                event(
                    TraceAction.PAUSE,
                    snapshot(phase=PlatformPhase.PAUSED),
                    snapshot(phase=PlatformPhase.PAUSED, x=10),
                )
            ],
            "pause",
        )
        is TraceStatus.FAILED
    )


def test_restart_leaking_old_keys_or_objects_is_failure():
    start = event(TraceAction.START, snapshot(phase=PlatformPhase.MENU), snapshot())
    restart = event(
        TraceAction.RESTART,
        snapshot(3, phase=PlatformPhase.LOST),
        snapshot(keys=frozenset(), objects=frozenset({"old-projectile"})),
    )
    assert status([start, restart], "restart") is TraceStatus.FAILED


def test_unreachable_or_missing_observations_are_unverified():
    report = verify_trace(())
    assert report.status is TraceStatus.UNVERIFIED
    assert not report.complete
    assert all(item.status is TraceStatus.UNVERIFIED for item in report.criteria)


def test_mutating_evidence_cannot_prove_gate():
    observation = event(TraceAction.MOVE, snapshot(), snapshot(x=10), snapshot())
    observation = replace(observation, read_only=False)
    assert status([observation], "movement") is TraceStatus.UNVERIFIED


def test_full_observed_three_level_route_and_restart_pass():
    base = snapshot()
    empty = frozenset()
    events = [
        event(TraceAction.START, snapshot(phase=PlatformPhase.MENU), base),
        event(TraceAction.MOVE, base, snapshot(x=10), base),
        event(TraceAction.JUMP, base, snapshot(y=-10), base),
        event(TraceAction.DOOR, snapshot(contact=True), base),
        event(TraceAction.DOOR, snapshot(keys=empty, contact=True), snapshot(2)),
        event(TraceAction.DOOR, snapshot(2, keys=empty, contact=True), snapshot(3)),
        event(
            TraceAction.DOOR,
            snapshot(3, keys=empty, contact=True),
            snapshot(3, phase=PlatformPhase.WON, keys=empty),
        ),
        event(
            TraceAction.PAUSE,
            snapshot(phase=PlatformPhase.PAUSED),
            snapshot(phase=PlatformPhase.PAUSED),
        ),
        event(TraceAction.RESUME, snapshot(phase=PlatformPhase.PAUSED), base),
        event(TraceAction.WAIT, base, snapshot(phase=PlatformPhase.LOST, hp=0)),
        event(TraceAction.RESTART, snapshot(phase=PlatformPhase.LOST, hp=0), base),
    ]
    report = verify_trace(tuple(events))
    assert report.status is TraceStatus.PASSED
    assert report.complete


def test_mutating_extra_event_leaves_trace_integrity_unverified():
    before = snapshot()
    trace = (
        event(TraceAction.MOVE, before, snapshot(x=10), before),
        replace(event(TraceAction.MOVE, before, snapshot(x=20), before), read_only=False),
    )
    assert status(trace, "trace_integrity") is TraceStatus.UNVERIFIED


@pytest.mark.parametrize("action", [TraceAction.MOVE, TraceAction.WAIT])
def test_non_door_level_skip_fails_even_when_other_criteria_pass(action):
    base = snapshot()
    empty = frozenset()
    events = [
        event(TraceAction.START, snapshot(phase=PlatformPhase.MENU), base),
        event(TraceAction.MOVE, base, snapshot(x=10), base),
        event(TraceAction.JUMP, base, snapshot(y=-10), base),
        event(TraceAction.DOOR, snapshot(contact=True), base),
        event(TraceAction.DOOR, snapshot(keys=empty, contact=True), snapshot(2)),
        event(TraceAction.DOOR, snapshot(2, keys=empty, contact=True), snapshot(3)),
        event(
            TraceAction.DOOR,
            snapshot(3, keys=empty, contact=True),
            snapshot(3, phase=PlatformPhase.WON, keys=empty),
        ),
        event(
            TraceAction.PAUSE,
            snapshot(phase=PlatformPhase.PAUSED),
            snapshot(phase=PlatformPhase.PAUSED),
        ),
        event(TraceAction.RESUME, snapshot(phase=PlatformPhase.PAUSED), base),
        event(TraceAction.WAIT, base, snapshot(phase=PlatformPhase.LOST, hp=0)),
        event(TraceAction.RESTART, snapshot(phase=PlatformPhase.LOST, hp=0), base),
        event(action, base, snapshot(3, x=10), base),
    ]
    assert verify_trace(tuple(events)).status is TraceStatus.FAILED

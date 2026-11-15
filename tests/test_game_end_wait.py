"""Missing game hooks are unmeasurable, not a reason to poll a whole game timeout."""

from __future__ import annotations

from fusion_cli.tools import game_hud
from fusion_cli.tools.play_probe import ProbeReport


class _StatePage:
    """A page boundary with observed states and virtual timeout recording."""

    def __init__(self, states):
        self.states = states
        self.evaluations = 0
        self.waits = []

    async def evaluate(self, script):
        assert script == "fixture-state"
        state = self.states[min(self.evaluations, len(self.states) - 1)]
        self.evaluations += 1
        return state

    async def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)


async def test_missing_state_hook_returns_unmeasured_without_waiting():
    page = _StatePage([None])

    result = await game_hud.restart_after_end(page, "fixture-state")

    assert result == ()
    assert page.evaluations == 1
    assert page.waits == []


async def test_disappearing_state_hook_stops_polling_as_unmeasured():
    page = _StatePage(['{"state":"playing"}', None])

    result = await game_hud.restart_after_end(page, "fixture-state")

    assert result == ()
    assert page.evaluations == 2
    assert page.waits == [game_hud.END_POLL_MS]


async def test_available_playing_state_keeps_existing_end_wait_budget():
    page = _StatePage(['{"state":"playing"}'])

    result = await game_hud.restart_after_end(page, "fixture-state")

    assert result == ()
    assert sum(page.waits) == game_hud.END_WAIT_MS == 45_000
    assert all(wait == game_hud.END_POLL_MS for wait in page.waits)
    assert page.evaluations > 1


def test_unmeasured_hook_does_not_become_a_claim_of_restart_success():
    report = ProbeReport((), 60, None, None, None, None, ended_checked=True)

    assert "window.__GAME_STATE__ yok" in report.summary()
    assert "sorun ölçülmedi (ya da oyun bitmedi)" in report.summary()

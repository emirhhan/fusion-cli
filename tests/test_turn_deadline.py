"""Dış isteğin mutlak süresi yerel saatte tek kez kurulur."""

from __future__ import annotations

import pytest

from fusion_cli.core.turn_deadline import TurnDeadline


class FakeClock:
    def __init__(self, value: float = 0.0):
        self.value = value

    def monotonic(self) -> float:
        return self.value

    def now(self) -> float:
        return self.value


@pytest.mark.parametrize("duration", [True, False, -1, 0, float("nan"), float("inf"), "5", 10**400])
def test_external_duration_rejects_invalid_nonfinite_or_nonpositive_values(duration):
    with pytest.raises(ValueError):
        TurnDeadline.from_duration(duration, FakeClock())


def test_duration_is_derived_once_in_server_clock_domain_and_absence_is_compatible():
    clock = FakeClock(100)
    deadline = TurnDeadline.from_duration(10, clock)
    assert deadline is not None
    assert deadline.remaining_s() == 10
    clock.value = 104
    assert deadline.remaining_s() == 6
    clock.value = 111
    assert deadline.remaining_s() == -1
    assert TurnDeadline.from_duration(None, clock) is None


def test_existing_budget_is_only_tightened_without_resetting_origin():
    from fusion_cli.core.budget import TurnBudget

    clock = FakeClock()
    budget = TurnBudget(clock, 10, 2, 2, 2, 2, 2, total_timeout_s=4)
    clock.value = 2
    budget.constrain_remaining_s(10)
    assert budget.total_timeout_s == 4
    budget.constrain_remaining_s(1)
    assert budget.total_timeout_s == 3
    assert budget.elapsed_s == 2

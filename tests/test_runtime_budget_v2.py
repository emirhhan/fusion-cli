from __future__ import annotations

import pytest

from fusion_cli.core.budget import BudgetStop, TurnBudget
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.execution_policy import policy_for

from .fakes import make_config


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value


def budget(clock: FakeClock, **overrides) -> TurnBudget:
    values = {
        "max_model_calls": 50,
        "max_verify_rounds": 2,
        "max_empty_retries": 2,
        "max_contract_repairs": 1,
        "max_auto_continues": 1,
        "max_idle_rounds": 3,
    }
    values.update(overrides)
    return TurnBudget(clock=clock, **values)


def test_progress_idle_saatini_tazeler_ama_hard_cap_tazelenmez():
    clock = FakeClock()
    b = budget(
        clock,
        total_timeout_s=20.0,
        idle_timeout_s=5.0,
    )

    clock.value = 4.0
    b.record_round(progressed=True)

    clock.value = 8.5
    assert b.time_stop_reason() is None
    assert b.elapsed_s == pytest.approx(8.5)
    assert b.idle_elapsed_s == pytest.approx(4.5)

    clock.value = 9.1
    assert b.time_stop_reason() is BudgetStop.INACTIVITY


def test_hard_cap_progress_ile_tazelenmez():
    clock = FakeClock()
    b = budget(
        clock,
        total_timeout_s=10.0,
        idle_timeout_s=5.0,
    )

    clock.value = 4.0
    b.record_round(progressed=True)

    clock.value = 8.0
    b.record_round(progressed=True)

    clock.value = 10.1
    assert b.time_stop_reason() is BudgetStop.DEADLINE


def test_next_timeout_en_yakin_deadline_i_secer():
    clock = FakeClock()
    b = budget(
        clock,
        total_timeout_s=20.0,
        idle_timeout_s=5.0,
    )

    clock.value = 2.0
    assert b.next_timeout_s() == pytest.approx(3.0)

    b.record_round(progressed=True)
    clock.value = 4.0

    assert b.next_timeout_s() == pytest.approx(3.0)


def test_web_policy_hard_ve_idle_limitlerini_ayirir():
    config = make_config(
        agent=ModelSpec(name="agent", model="gemini_web/main/auto"),
        task_model_map={},
    )
    spec = config.agent

    simple = policy_for(
        config,
        spec,
        TaskKind.EXPLORE,
        "klasörü listele",
    )
    complex_ = policy_for(
        config,
        spec,
        TaskKind.BUGFIX,
        "hatayı düzelt",
    )
    extended = policy_for(
        config,
        spec,
        TaskKind.BUGFIX,
        "tüm projeyi kapsamlı düzelt",
    )

    assert simple.total_timeout_s == 240.0
    assert simple.idle_timeout_s == 120.0

    assert complex_.total_timeout_s == 1800.0
    assert complex_.idle_timeout_s == 240.0

    assert extended.total_timeout_s == 2400.0
    assert extended.idle_timeout_s == 300.0

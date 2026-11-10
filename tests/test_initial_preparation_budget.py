"""Initial preparation may consume idle time, but never renew a used turn budget."""

from __future__ import annotations

import pytest

from fusion_cli.core.budget import BudgetStop, TurnBudget
from fusion_cli.engines.agent import loop

from .fakes import RecordingSink, ScriptedProvider, model_result
from .test_turn_budget import _budget, _deps, _FakeClock, _kur


def _prepared_turn(monkeypatch, tmp_path):
    clock = _FakeClock()
    deps = _deps(tmp_path, RecordingSink())
    deps.budget = _budget(clock, total_timeout_s=5.0, idle_timeout_s=0.1)
    provider = _kur(monkeypatch, ScriptedProvider([model_result("tamamlanmış cevap")]))
    bind = loop._bind_tool_search_permissions

    def prepare(*args, **kwargs):
        permitted = bind(*args, **kwargs)
        # Deterministic preparation beyond the idle window; no wall-clock race.
        clock.value += 0.11
        return permitted

    monkeypatch.setattr(loop, "_bind_tool_search_permissions", prepare)
    return deps, provider, clock


async def test_initial_preparation_expired_idle_still_dispatches_first_call(monkeypatch, tmp_path):
    deps, provider, _clock = _prepared_turn(monkeypatch, tmp_path)

    result = await loop.run_agent("merhaba", deps, chat_mode=True, self_review=False, verify=False)

    assert result.ok
    assert result.final_text == "tamamlanmış cevap"
    assert provider.calls == deps.budget.model_calls == 1
    assert deps.budget.stop is None
    assert deps.budget._started_at == 0.0


async def test_initial_preparation_never_recovers_expired_hard_deadline(monkeypatch, tmp_path):
    deps, provider, _clock = _prepared_turn(monkeypatch, tmp_path)
    deps.budget.total_timeout_s = 0.1

    result = await loop.run_agent("merhaba", deps, chat_mode=True, self_review=False, verify=False)

    assert not result.ok
    assert result.stop_reason == "deadline"
    assert provider.calls == deps.budget.model_calls == 0


@pytest.mark.parametrize("internal", [False, True])
async def test_used_shared_budget_does_not_recover_idle(monkeypatch, tmp_path, internal):
    deps, provider, _clock = _prepared_turn(monkeypatch, tmp_path)
    assert deps.budget.reserve_model_call()

    result = await loop.run_agent(
        "merhaba", deps, chat_mode=True, internal=internal, self_review=False, verify=False
    )

    assert not result.ok
    assert result.stop_reason == "inactivity"
    assert provider.calls == 0
    assert deps.budget.model_calls == 1


@pytest.mark.parametrize("stop", [BudgetStop.INACTIVITY, BudgetStop.NO_PROGRESS])
async def test_initial_preparation_does_not_revive_latched_stop(monkeypatch, tmp_path, stop):
    deps, provider, _clock = _prepared_turn(monkeypatch, tmp_path)
    deps.budget.stop = stop

    result = await loop.run_agent("merhaba", deps, chat_mode=True, self_review=False, verify=False)

    assert not result.ok
    assert result.stop_reason == stop.value
    assert provider.calls == deps.budget.model_calls == 0


@pytest.mark.parametrize("cap", ["shared", "child"])
async def test_initial_preparation_does_not_bypass_call_caps(monkeypatch, tmp_path, cap):
    deps, provider, _clock = _prepared_turn(monkeypatch, tmp_path)
    if cap == "shared":
        deps.budget.max_model_calls = 0

    result = await loop.run_agent(
        "merhaba",
        deps,
        chat_mode=True,
        self_review=False,
        verify=False,
        internal=cap == "child",
        depth=1 if cap == "child" else 0,
        step_limit=0 if cap == "child" else None,
    )

    assert not result.ok
    assert result.stop_reason == "model_calls"
    assert provider.calls == deps.budget.model_calls == 0


async def test_hard_deadline_crossing_during_initial_credit_still_blocks_call(
    monkeypatch, tmp_path
):
    deps, provider, clock = _prepared_turn(monkeypatch, tmp_path)
    progress = TurnBudget.record_progress

    def credit(budget):
        if budget is deps.budget:
            clock.value = 5.0
        progress(budget)

    monkeypatch.setattr(TurnBudget, "record_progress", credit)

    result = await loop.run_agent("merhaba", deps, chat_mode=True, self_review=False, verify=False)

    assert not result.ok
    assert result.stop_reason == "deadline"
    assert provider.calls == deps.budget.model_calls == 0

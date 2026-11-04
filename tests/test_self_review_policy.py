"""The shared eligibility decision preserves overrides and existing exclusions."""

from __future__ import annotations

import pytest

from fusion_cli.core.budget import BudgetStop, TurnBudget
from fusion_cli.core.clock import SystemClock
from fusion_cli.engines.agent.loop import AgentOutcome


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, True),
        ({"configured": False, "override": True}, True),
        ({"override": False}, False),
        ({"stop": BudgetStop.USER_DENIED}, False),
        ({"stop": BudgetStop.CONTRACT_UNREPAIRABLE}, True),
        ({"tool": "chrome_click"}, False),
        ({"tool": "claude-in-chrome__click"}, False),
        ({"tool": "browser_click"}, False),
        ({"wrong_workspace": True}, False),
        ({"measurement_failure": True}, False),
        ({"plan_mode": True}, False),
        ({"depth": 1}, False),
        ({"final_text": "  "}, False),
        ({"mutations": 0}, False),
    ],
)
def test_ordinary_review_eligibility_uses_current_structural_state(changes, expected):
    from fusion_cli.engines.agent.self_review_policy import ordinary_self_review_enabled

    budget = TurnBudget(
        clock=SystemClock(),
        max_model_calls=10,
        max_verify_rounds=2,
        max_empty_retries=1,
        max_contract_repairs=1,
        max_auto_continues=1,
        max_idle_rounds=10,
    )
    budget.successful_tool_evidence.append((changes.get("tool", "write_file"), {}, True))
    budget.stop = changes.get("stop")
    outcome = AgentOutcome(
        changes.get("final_text", "Dosya oluşturuldu"),
        [],
        mutating_tool_calls_made=changes.get("mutations", 1),
        wrong_workspace=changes.get("wrong_workspace", False),
    )
    result = ordinary_self_review_enabled(
        outcome,
        budget,
        configured=changes.get("configured", True),
        override=changes.get("override"),
        plan_mode=changes.get("plan_mode", False),
        depth=changes.get("depth", 0),
        measurement_failure=changes.get("measurement_failure", False),
        browser_prefixes=("chrome_", "claude-in-chrome__", "browser_"),
    )
    assert result is expected

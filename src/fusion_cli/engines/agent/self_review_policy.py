"""One structural eligibility decision for ordinary review and review deduplication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.budget import BudgetStop, TurnBudget

if TYPE_CHECKING:
    from .loop import AgentOutcome


def ordinary_self_review_enabled(
    outcome: AgentOutcome,
    budget: TurnBudget,
    *,
    configured: bool,
    override: bool | None,
    plan_mode: bool,
    depth: int,
    measurement_failure: bool,
    browser_prefixes: tuple[str, ...],
) -> bool:
    """Preserve the existing loop's exact override and structural exclusions.

    Only USER_DENIED suppresses review by budget state. A late transport/contract
    stop must not silently leave an existing file mutation unreviewed.
    """
    enabled = configured if override is None else override
    if not enabled or outcome.mutating_tool_calls_made == 0:
        return False
    if all(
        name.startswith(browser_prefixes)
        for name, _args, mutating in budget.successful_tool_evidence
        if mutating
    ):
        return False
    if budget.stop is BudgetStop.USER_DENIED:
        return False
    if outcome.wrong_workspace or measurement_failure:
        return False
    return not plan_mode and depth == 0 and bool(outcome.final_text.strip())

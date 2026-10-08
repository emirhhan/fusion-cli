"""Araç kanıtını mevcut tur bütçesine bağlayan kısa karar noktası."""

from __future__ import annotations

from dataclasses import dataclass

from ...core.budget import BudgetStop, TurnBudget
from ...core.repair_ledger import RepairAction
from ...core.tools import ToolResult


@dataclass(frozen=True, slots=True)
class RepairFeedback:
    """Sohbetten bağımsız kayıt kısa not ve ilerleme sinyali üretir."""

    is_new_failure: bool = False
    is_exhausted: bool = False
    note: str = ""


def record_failure_evidence(result: ToolResult, budget: TurnBudget) -> RepairFeedback:
    """Bir bağımsız ölçümdeki birden çok bulgu için tek onarım hakkı tüket."""
    if result.ok or not result.failure_evidence:
        return RepairFeedback()
    remaining = max(0, budget.max_verify_rounds - budget.verify_rounds)
    decisions = tuple(
        budget.repair_ledger.observe(item, remaining_repairs=remaining)
        for item in result.failure_evidence
    )
    new = any(
        item.action not in {RepairAction.ALREADY_OBSERVED, RepairAction.EXCLUDED}
        for item in decisions
    )
    exhausted = any(item.action is RepairAction.EXHAUSTED for item in decisions)
    if exhausted:
        budget.halt(BudgetStop.NO_PROGRESS)
    elif new:
        budget.take_verify_round()
    notes = tuple(dict.fromkeys(item.note for item in decisions if item.note))
    return RepairFeedback(new, exhausted, "\n".join(notes))

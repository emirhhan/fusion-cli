"""Ayrılmış doğrulama hakkına yeni bütçe eklemeden typed bulguyu kaydeder."""

from __future__ import annotations

from ...core.budget import TurnBudget
from ...core.verification import VerificationResult


def observe_verifier_failures(result: VerificationResult, budget: TurnBudget) -> str:
    """Bu ölçümün correction hakkı ayrılmıştır; burada hak tüketme veya durdurma yok."""
    if result.ok:
        return ""
    notes = []
    for evidence in result.failure_evidence:
        # Bir hak mevcut ölçüm için önceden ayrıldı; sonraki ölçümü loop sınırlar.
        decision = budget.repair_ledger.observe(evidence, remaining_repairs=1)
        if decision.note and decision.note not in notes:
            notes.append(decision.note)
    return "\n".join(notes)

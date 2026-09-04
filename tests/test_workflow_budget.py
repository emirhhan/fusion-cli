"""Profesyonel workflow'un bağımsız çağrı bütçesi zarfları."""

from __future__ import annotations

from fusion_cli.engines.workflow.model import (
    BudgetEnvelope,
    BudgetLedger,
    WorkflowBudget,
)


def test_zarflar_birbirinden_bagimsiz_tukenir():
    ledger = BudgetLedger(WorkflowBudget(planning=1, per_step=2, recovery=1, final=1))

    assert ledger.charge(BudgetEnvelope.PLANNING, 1).allowed is True
    assert ledger.charge(BudgetEnvelope.PLANNING, 1).allowed is False
    assert ledger.charge(BudgetEnvelope.PER_STEP, 1).allowed is True


def test_tam_sinir_kabul_edilir_fazlasi_reddedilir():
    ledger = BudgetLedger(WorkflowBudget(planning=2, per_step=3, recovery=1, final=1))

    decision = ledger.charge(BudgetEnvelope.PER_STEP, 3)

    assert decision.allowed is True
    assert decision.remaining == 0
    assert ledger.charge(BudgetEnvelope.PER_STEP, 1).allowed is False


def test_reddedilen_harcama_sayaci_asmaz():
    ledger = BudgetLedger(WorkflowBudget(planning=1, per_step=1, recovery=1, final=1))

    ledger.charge(BudgetEnvelope.FINAL, 2)

    assert ledger.used(BudgetEnvelope.FINAL) == 0

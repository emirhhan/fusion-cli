"""Paralel deneme plan yürütücüsüne bağlı.

Seçim kuralı tek başına yetmez: adım gerçekten N kez, izole kopyalarda koşmalı;
kazanan asıl projeye uygulanmalı; kaybeden hiçbir aday dosyaya dokunmamalı.
Bütçe de ayrı bir zarftan harcanmalı — deneme sayısı adım zarfını yiyip planın
kalanını aç bırakmamalı.
"""

from __future__ import annotations

from fusion_cli.engines.workflow.model import BudgetEnvelope, BudgetLedger, WorkflowBudget


def test_deneme_zarfi_ayri_hesaplanir():
    butce = WorkflowBudget(attempts=6)
    ledger = BudgetLedger(butce)

    assert butce.limit_for(BudgetEnvelope.ATTEMPTS) == 6
    assert ledger.charge(BudgetEnvelope.ATTEMPTS, 4).allowed
    assert not ledger.charge(BudgetEnvelope.ATTEMPTS, 4).allowed


def test_deneme_harcamasi_adim_zarfini_yemez():
    ledger = BudgetLedger(WorkflowBudget(per_step=5, attempts=6))

    ledger.charge(BudgetEnvelope.ATTEMPTS, 6)

    assert ledger.charge(BudgetEnvelope.PER_STEP, 5, scope="adim").allowed


def test_varsayilan_deneme_zarfi_sifirdir():
    """Paralel deneme OPT-IN'dir: yapılandırılmadan ek çağrı harcanmaz."""
    assert WorkflowBudget().attempts == 0

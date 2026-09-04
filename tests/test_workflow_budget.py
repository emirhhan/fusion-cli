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


def test_adim_zarfi_her_adim_icin_bagimsiz_sayilir():
    """Ölçüldü (Godot koşusu): `per_step` tüm plan için TEK sayaçtı.

    Dört adımlık planın ilk adımı sekiz çağrının hepsini harcadı; kalan üç adım
    hiç başlayamadan workflow duraklatıldı. Alan adı da yapılandırma açıklaması
    da "her adımın bağımsız zarfı" diyor; sayaç bunu izlemeliydi.
    """
    ledger = BudgetLedger(WorkflowBudget(planning=1, per_step=2, recovery=1, final=1))

    assert ledger.charge(BudgetEnvelope.PER_STEP, 2, scope="adim-1").allowed is True
    assert ledger.charge(BudgetEnvelope.PER_STEP, 1, scope="adim-1").allowed is False
    assert ledger.charge(BudgetEnvelope.PER_STEP, 2, scope="adim-2").allowed is True


def test_kurtarma_zarfi_da_her_adim_icin_bagimsiz_sayilir():
    """Tasarım "adım kurtarma" zarfı diyor: tek bir tökezleyen adım tüm planın
    onarım hakkını yiyemez. Ölçüldü: üçüncü-parti MCP'nin tek hatası, henüz hiç
    başlamamış adımların kurtarma hakkını da tüketip planı duraklattı."""
    ledger = BudgetLedger(WorkflowBudget(planning=1, per_step=2, recovery=1, final=1))

    assert ledger.charge(BudgetEnvelope.RECOVERY, 1, scope="adim-1").allowed is True
    assert ledger.charge(BudgetEnvelope.RECOVERY, 1, scope="adim-1").allowed is False
    assert ledger.charge(BudgetEnvelope.RECOVERY, 1, scope="adim-2").allowed is True


def test_plan_geneli_zarflar_kapsam_almaz():
    """Planlama ve final kapısı plan başına TEK haktır."""
    ledger = BudgetLedger(WorkflowBudget(planning=1, per_step=2, recovery=1, final=1))

    assert ledger.charge(BudgetEnvelope.FINAL, 1, scope="adim-1").allowed is True
    assert ledger.charge(BudgetEnvelope.FINAL, 1, scope="adim-2").allowed is False


def test_adim_zarfinin_harcamasi_kendi_kapsaminda_okunur():
    ledger = BudgetLedger(WorkflowBudget(planning=1, per_step=3, recovery=1, final=1))

    ledger.charge(BudgetEnvelope.PER_STEP, 2, scope="adim-1")

    assert ledger.used(BudgetEnvelope.PER_STEP, scope="adim-1") == 2
    assert ledger.used(BudgetEnvelope.PER_STEP, scope="adim-2") == 0

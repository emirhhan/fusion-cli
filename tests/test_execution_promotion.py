"""Hızlı başlayan görevin çalışma kanıtıyla profesyonel akışa yükselmesi."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.promotion import ExecutionSignals, should_promote


@pytest.mark.parametrize(
    ("signals", "reason"),
    [
        (ExecutionSignals(pending_todos=3), "üç veya daha fazla bekleyen iş"),
        (ExecutionSignals(touched_components=2), "birden fazla bileşen"),
        (ExecutionSignals(tool_families=2), "birden fazla araç ailesi"),
        (ExecutionSignals(has_dependency=True), "araç çıktısına bağlı sonraki iş"),
        (ExecutionSignals(needs_repair=True), "teşhis ve onarım gerektiren hata"),
        (ExecutionSignals(needs_verification=True), "ayrı doğrulama gereksinimi"),
        (ExecutionSignals(budget_pressure=True), "hızlı yol bütçesi yetersiz"),
    ],
)
def test_karmaşıklık_sinyali_workflowa_yukseltir(signals, reason):
    decision = should_promote(signals)

    assert decision.should_promote is True
    assert decision.reasons == (reason,)


def test_sinyal_yoksa_hizli_yol_devam_eder():
    decision = should_promote(ExecutionSignals())

    assert decision.should_promote is False
    assert decision.reasons == ()


def test_birden_fazla_sinyal_tum_gerekceleri_kararli_sirada_tasir():
    decision = should_promote(
        ExecutionSignals(pending_todos=4, tool_families=2, needs_repair=True)
    )

    assert decision.reasons == (
        "üç veya daha fazla bekleyen iş",
        "birden fazla araç ailesi",
        "teşhis ve onarım gerektiren hata",
    )

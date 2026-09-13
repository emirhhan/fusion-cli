"""Dosya teslim eden adımın kanıtı, DEĞİŞTİREN bir araç çağrısıdır.

Ölçüldü (13 Eylül, Godot koşusu): adım `file:ASSETS.json` bekliyordu; model tek
bir `web_search` yaptı ve "assetleri bulup indireceğim" diyen bir metinle turu
bitirdi. Kanıt kapısı bunu yeterli saydı, yeniden istem yapılmadı, hiçbir dosya
yazılmadı ve adım doğrulamada düştü.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.budget import TurnBudget
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _tool_evidence_satisfied


class _SabitSaat:
    """Testin ilerletmediği saat; bu testler süreyle ilgilenmiyor."""

    def monotonic(self) -> float:
        return 0.0


def _butce(*kayitlar: tuple[str, bool]) -> TurnBudget:
    butce = TurnBudget(
        clock=_SabitSaat(),
        max_model_calls=50,
        max_verify_rounds=2,
        max_empty_retries=2,
        max_contract_repairs=1,
        max_auto_continues=1,
        max_idle_rounds=3,
    )
    for ad, degistiren in kayitlar:
        butce.successful_tool_evidence.append((ad, {}, degistiren))
    return butce


def _politika(effect: str) -> ExecutionPolicy:
    return ExecutionPolicy(is_web=True, required_effect=effect, requires_tool_evidence=True)


def test_arama_dosya_teslimini_kanitlamaz():
    butce = _butce(("web_search", False))

    assert not _tool_evidence_satisfied(_politika("file:ASSETS.json"), butce)


def test_yazma_dosya_teslimini_kanitlar():
    assert _tool_evidence_satisfied(_politika("file:ASSETS.json"), _butce(("write_file", True)))


def test_indirme_dosya_teslimini_kanitlar():
    """`download_file` değiştiricidir: dosyayı diske yazar."""
    assert _tool_evidence_satisfied(_politika("file:assets/a.png"), _butce(("download_file", True)))


def test_hic_arac_cagrilmadiysa_kanit_yok():
    assert not _tool_evidence_satisfied(_politika("file:a.txt"), _butce())


@pytest.mark.parametrize(
    "effect,kayit,beklenen",
    [
        ("web_lookup", ("web_search", False), True),
        ("web_lookup", ("write_file", True), False),
        ("workspace_mutation", ("write_file", True), True),
        ("workspace_read", ("list_dir", False), True),
    ],
)
def test_diger_etkiler_degismedi(effect, kayit, beklenen):
    assert _tool_evidence_satisfied(_politika(effect), _butce(kayit)) is beklenen

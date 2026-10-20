"""Nihai rapor metne indirgenmeden aynı tur sonucunda korunur."""

from dataclasses import FrozenInstanceError

import pytest

from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop

from .test_plan_job_delivery import execute_plan
from .test_plan_runner import _FakeDeps


def test_legacy_outcome_without_report_does_not_invent_completion_evidence():
    outcome = loop.AgentOutcome(final_text="Yanıt", messages=[])
    assert outcome.completion_report is None


@pytest.mark.parametrize("exit_code", [0, 1])
def test_ordinary_outcome_retains_computed_report_and_blocking_verdict(tmp_path, exit_code):
    context = ToolContext(tmp_path)
    context.changes.record(tmp_path / "a.py")
    uses = (
        ToolUse("write_file", mutating=True, arguments={"path": "a.py"}),
        ToolUse(
            "run_shell",
            ok=exit_code == 0,
            mutating=True,
            arguments={"command": "pytest -q"},
            output=f"(çıkış kodu {exit_code})\nkanıt",
        ),
    )
    outcome = loop.AgentOutcome(final_text="Görev yanıtı", messages=[], tool_uses=uses)
    loop._apply_turn_report(outcome, _FakeDeps(context), gate=VerificationResult(ok=exit_code == 0))
    report = outcome.completion_report
    assert report is not None
    assert report.changed_paths == ("a.py",)
    assert report.is_verified is (exit_code == 0)
    assert report.blocks_success is (exit_code != 0)
    assert outcome.ok is (exit_code == 0)
    with pytest.raises(FrozenInstanceError):
        report.false_claim = True


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["unchanged", "output", "nonzero"])
async def test_plan_retains_consolidated_current_delivery_report(tmp_path, change):
    outcome, _, receipts = await execute_plan(tmp_path, change)
    report = outcome.completion_report
    assert report is not None
    assert len(report.job_deliveries) == 1
    delivery = report.job_deliveries[0]
    assert delivery.completion == receipts[0]
    # Güncel çıktı ölçümü yalnız başarıyla biten işe alınır; başarısız işin sorunu
    # çıkış kodudur ve onun çıktısını yeniden ölçmek bir şey kanıtlamaz.
    assert (delivery.current is not None) is (change != "nonzero")
    if change == "unchanged":
        assert outcome.ok and not report.blocks_success and not delivery.problem
    else:
        assert not outcome.ok and report.blocks_success and delivery.problem


def test_kits_icin_kanit_ozeti_rapordan_uretilir(tmp_path):
    """Kits fusion_run sonucunda yalnız metin görüyordu; doğrulanmamış iş "tamam" gibi
    sunulabiliyordu. Tur cevabı artık rapordan yapılandırılmış kanıt taşır."""
    from fusion_cli.engines.agent.turn_report import evidence_payload

    assert evidence_payload(None) is None
    context = ToolContext(tmp_path)
    context.changes.record(tmp_path / "a.py")
    uses = (
        ToolUse("write_file", mutating=True, arguments={"path": "a.py"}),
        ToolUse(
            "run_shell", ok=False, mutating=True, arguments={"command": "pytest -q"},
            output="(çıkış kodu 1)\nhata",
        ),
    )  # fmt: skip
    outcome = loop.AgentOutcome(final_text="Bitti, testler geçti.", messages=[], tool_uses=uses)
    loop._apply_turn_report(outcome, _FakeDeps(context), gate=VerificationResult(ok=False))
    kanit = evidence_payload(outcome.completion_report)
    assert kanit == {
        "schema_version": 1,
        "degisen_sayisi": 1,
        "degisen_kisaltildi": False,
        "sorun_sayisi": 0,
        "sorunlar_kisaltildi": False,
        "dogrulandi": False,
        "engelliyor": True,
        "yanlis_iddia": True,
        "degisen": ["a.py"],
        "sorunlar": [],
    }

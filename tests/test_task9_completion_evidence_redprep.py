"""Paket 9 hazırlığı: teslim iddiası mevcut kanıt otoritesini yükseltemez."""

from __future__ import annotations

from evals.execution import TaskExecution
from evals.metrics import score_task
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.turn_report import CommandRun, TurnReport, evidence_payload


def test_empty_render_preserves_failed_gate_in_public_evidence() -> None:
    """Görünür rapor boş olsa da başarısız kapı başarı engeli olarak taşınır."""
    report = TurnReport(gate=VerificationResult(ok=False, findings=("Kontrol başarısız.",)))

    assert report.render() == ""
    assert report.blocks_success is True
    payload = evidence_payload(report)
    assert payload is not None
    assert payload["engelliyor"] is True
    assert payload["dogrulandi"] is not True


def test_failed_gate_never_projects_verified_delivery_despite_successful_command() -> None:
    """Geçen tek komut başarısız toplam kapıyı doğrulanmış teslim yapamaz."""
    report = TurnReport(
        changed_paths=("ornek.py",),
        command_runs=(CommandRun("pytest -q", exit_code=0, after_last_mutation=True),),
        gate=VerificationResult(ok=False, findings=("Başka davranış kontrolü başarısız.",)),
    )

    assert report.blocks_success is True
    payload = evidence_payload(report)
    assert payload is not None
    assert payload["engelliyor"] is True
    assert payload["dogrulandi"] is False


def test_success_before_latest_mutation_is_not_verified_delivery() -> None:
    """Eski başarı son değişikliğin davranış kanıtı değildir."""
    report = TurnReport(
        changed_paths=("ornek.py",),
        command_runs=(CommandRun("pytest -q", exit_code=0, after_last_mutation=False),),
        require_behavioral_evidence=True,
    )

    assert report.is_verified is False
    assert report.blocks_success is True


def test_unknown_command_exit_is_not_verified_delivery() -> None:
    """Çıkış kodu bilinmeyen kontrol tamamlanma kanıtı sayılmaz."""
    report = TurnReport(
        changed_paths=("ornek.py",),
        command_runs=(CommandRun("pytest -q", exit_code=None, after_last_mutation=True),),
        require_behavioral_evidence=True,
    )

    assert report.is_verified is False
    assert report.blocks_success is True


def test_claimed_completion_without_required_change_is_false_success() -> None:
    """Modelin bitti beyanı gözlenmeyen gerekli dosya değişikliğini üretemez."""
    task = EvalTask(
        id="teslim",
        request="Örnek dosyayı değiştir.",
        criterion=SuccessCriterion(kind=CriterionKind.FILE_CHANGED, expected_path="ornek.py"),
    )
    observation = TaskExecution(task_id=task.id, claimed_success=True)

    result = score_task(task, observation)

    assert result.success is False
    assert result.false_success is True


def test_failed_gate_report_never_prints_verified_delivery_heading() -> None:
    report = TurnReport(
        changed_paths=("ornek.py",),
        command_runs=(CommandRun("pytest -q", exit_code=0, after_last_mutation=True),),
        gate=VerificationResult(ok=False, findings=("Başka kontrol başarısız.",)),
    )
    assert "✓ Doğrulandı:" not in report.render()
    assert "pytest -q" in report.render()


def test_empty_display_report_still_blocks_runtime_success(tmp_path) -> None:
    from types import SimpleNamespace

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.loop import AgentOutcome, _apply_turn_report

    outcome = AgentOutcome(final_text="bitti", messages=[], ok=True)
    deps = SimpleNamespace(tool_context=ToolContext(root=tmp_path))
    _apply_turn_report(outcome, deps, gate=VerificationResult(ok=False, findings=("failed",)))
    assert outcome.ok is False
    assert outcome.completion_report.blocks_success


def test_evidence_summary_reports_its_schema_and_truncation() -> None:
    report = TurnReport(changed_paths=tuple(f"file-{index}.py" for index in range(60)))
    payload = evidence_payload(report)
    assert payload["schema_version"] == 1
    assert len(payload["degisen"]) == 50
    assert payload["degisen_sayisi"] == 60
    assert payload["degisen_kisaltildi"] is True

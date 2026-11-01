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


def test_completion_criteria_preserve_ids_status_and_bounded_totals():
    from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
    from fusion_cli.core.execution_plan import VerificationCheckKind

    criteria = tuple(
        CriterionEvidence(
            f"criterion-{index}",
            VerificationCheckKind.COMMAND,
            (EvidenceStatus.PASSED, EvidenceStatus.FAILED, EvidenceStatus.UNVERIFIED)[index % 3],
            "ölçüm",
        )
        for index in range(60)
    )
    payload = evidence_payload(TurnReport(criteria=criteria))
    assert payload["criteria_count"] == 60
    assert payload["criteria_truncated"] is True
    assert len(payload["criteria"]) == 50
    assert payload["criteria"][1]["criterion_id"] == "criterion-1"
    assert payload["criteria"][1]["status"] == "failed"
    assert payload["criteria_status_counts"] == {"passed": 20, "failed": 20, "unverified": 20}


async def test_plan_existing_criterion_ids_reach_client_projection(tmp_path):
    from dataclasses import replace

    from fusion_cli.core.execution_plan import (
        ExecutionPlan,
        VerificationCheck,
        VerificationCheckKind,
    )
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.plan_runner import run_execution_plan
    from tests.test_plan_runner import _FakeDeps, _step

    (tmp_path / "app.py").write_text("value = 1\n")
    step = replace(
        _step("read"),
        success_criteria=("found", "unbound"),
        verification_checks=(
            VerificationCheck("found", VerificationCheckKind.FILE_EXISTS, "app.py"),
        ),
    )

    async def agent(task, deps, **kwargs):
        return AgentOutcome("Dosya incelendi.", [], tool_calls_made=1)

    outcome = await run_execution_plan(
        "Dosyayı incele",
        _FakeDeps(ToolContext(tmp_path)),
        agent,
        plan=ExecutionPlan("p", "read", (step,)),
    )
    payload = evidence_payload(outcome.completion_report)
    assert [(item["criterion_id"], item["status"]) for item in payload["criteria"]] == [
        ("found", "passed"),
        ("unbound", "unverified"),
    ]
    assert payload["criteria_count"] == 2
    assert payload["dogrulandi"] is False


def test_all_gate_criterion_statuses_reach_actual_outcome_client_projection(tmp_path):
    from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
    from fusion_cli.core.execution_plan import VerificationCheckKind
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.loop import AgentOutcome, _apply_turn_report
    from tests.test_plan_runner import _FakeDeps

    criteria = tuple(
        CriterionEvidence(
            f"criterion-{status.value}",
            VerificationCheckKind.COMMAND,
            status,
            "ölçüm",
            step_id="step",
        )
        for status in EvidenceStatus
    )
    outcome = AgentOutcome("Durum raporu.", [])
    _apply_turn_report(
        outcome, _FakeDeps(ToolContext(tmp_path)), gate=VerificationResult(False, evidence=criteria)
    )
    payload = evidence_payload(outcome.completion_report)
    assert [item["status"] for item in payload["criteria"]] == ["passed", "failed", "unverified"]
    assert {item["step_id"] for item in payload["criteria"]} == {"step"}
    assert payload["engelliyor"] is True


def test_client_criterion_text_bound_reports_truncation():
    from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
    from fusion_cli.core.execution_plan import VerificationCheckKind

    criterion = CriterionEvidence(
        "criterion", VerificationCheckKind.COMMAND, EvidenceStatus.UNVERIFIED, "a" * 1000
    )
    payload = evidence_payload(TurnReport(criteria=(criterion,)))
    assert payload["criteria"][0]["criterion_id"] == "criterion"
    assert len(payload["criteria"][0]["summary"]) == 500
    assert payload["criteria"][0]["text_truncated"] is True


def test_client_folds_shared_criterion_checks_before_bounds_and_status_totals():
    from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
    from fusion_cli.core.execution_plan import VerificationCheckKind

    criteria = tuple(
        item
        for index in range(60)
        for item in (
            CriterionEvidence(
                f"criterion-{index}",
                VerificationCheckKind.COMMAND,
                EvidenceStatus.PASSED,
                "komut geçti",
                command=f"true {index}",
                step_id="step",
            ),
            CriterionEvidence(
                f"criterion-{index}",
                VerificationCheckKind.TOOL,
                EvidenceStatus.FAILED if index % 2 else EvidenceStatus.UNVERIFIED,
                "araç kanıtı eksik",
                step_id="step",
            ),
        )
    )
    payload = evidence_payload(TurnReport(criteria=criteria))
    assert payload["criteria_count"] == 60
    assert len(payload["criteria"]) == 50
    assert payload["criteria_truncated"] is True
    assert payload["criteria_status_counts"] == {"passed": 0, "failed": 30, "unverified": 30}
    assert payload["criteria"][0]["criterion_id"] == "criterion-0"
    assert payload["criteria"][0]["status"] == "unverified"

"""Kanıt özetinin sürümlü ve sınırlandırılmış istemci projeksiyonu."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.artifact_kind import artifact_only
from ...core.evidence import summarize_criteria

if TYPE_CHECKING:
    from ...core.evidence import CriterionEvidence
    from .turn_report import TurnReport


#: Kits'e giden kanıt özetindeki liste tavanları (protokol satırı küçük kalır).
EVIDENCE_MAX_PATHS = 50
EVIDENCE_MAX_PROBLEMS = 10
EVIDENCE_MAX_CRITERIA = 50
EVIDENCE_MAX_TEXT = 500


def _client_criterion(item: CriterionEvidence) -> dict[str, object]:
    """Tek koşulu metin sınırlarını ve mevcut kimlik referanslarını koruyarak yansıt."""
    return {
        "criterion_id": item.criterion_id[:EVIDENCE_MAX_TEXT],
        "step_id": item.step_id[:EVIDENCE_MAX_TEXT],
        "text_truncated": any(
            len(value) > EVIDENCE_MAX_TEXT
            for value in (
                item.criterion_id,
                item.step_id,
                item.summary,
                item.call_id,
                item.source_digest,
            )
        ),
        "status": item.status.value,
        "summary": item.summary[:EVIDENCE_MAX_TEXT],
        "applicable": item.applicable,
        "source_digest": item.source_digest[:EVIDENCE_MAX_TEXT],
        "call_id": item.call_id[:EVIDENCE_MAX_TEXT],
    }


def evidence_payload(report: TurnReport | None) -> dict[str, object] | None:
    """Tur raporunun Kits gibi istemcilere giden yapılandırılmış kanıt özeti.

    Kits `fusion_run` sonucunda yalnız metni görüyordu: "testler geçti" diyen ama
    kanıtı olmayan bir tur başarılı gibi sunulabiliyordu. `None`: rapor yok (sohbet).
    """
    if report is None:
        return None
    if (
        not report.changed_paths
        and not report.command_runs
        and not report.criteria
        and not report.job_deliveries
        and not report.test_tamper
        and not report.blocks_success
        and (report.gate is None or (not report.gate.has_notes and not report.gate.evidence))
    ):
        return None
    criteria = summarize_criteria(report.criteria)
    problems = [item.problem for item in report.job_deliveries if item.problem]
    if report.gate is not None and not report.gate.ok:
        problems.extend(report.gate.findings)
    payload: dict[str, object] = {
        "schema_version": 1,
        "teslim_turu": "artifact" if artifact_only(report.changed_paths) else "code",
        "criteria": [_client_criterion(item) for item in criteria[:EVIDENCE_MAX_CRITERIA]],
        "criteria_count": len(criteria),
        "criteria_truncated": len(criteria) > EVIDENCE_MAX_CRITERIA,
        "criteria_status_counts": {
            status: sum(item.status.value == status for item in criteria)
            for status in ("passed", "failed", "unverified")
        },
        "dogrulandi": report.is_verified,
        "engelliyor": report.blocks_success,
        "yanlis_iddia": report.false_claim,
        "degisen": list(report.changed_paths[:EVIDENCE_MAX_PATHS]),
        "degisen_sayisi": len(report.changed_paths),
        "degisen_kisaltildi": len(report.changed_paths) > EVIDENCE_MAX_PATHS,
        "uyarilar": [
            item[:EVIDENCE_MAX_TEXT]
            for item in (report.gate.warnings if report.gate is not None else ())
        ][:EVIDENCE_MAX_PROBLEMS],
        "sorunlar": problems[:EVIDENCE_MAX_PROBLEMS],
        "sorun_sayisi": len(problems),
        "sorunlar_kisaltildi": len(problems) > EVIDENCE_MAX_PROBLEMS,
    }
    if report.test_tamper:
        # Yalnız bulgu varken eklenir: şemayı bekleyen istemciler için eklemeli alan.
        payload["supheli_test_degisikligi"] = {
            "adet": len(report.test_tamper),
            "zayiflatan": sum(1 for item in report.test_tamper if item.weakens),
            "turler": sorted({item.kind.value for item in report.test_tamper}),
            "yollar": [item.path for item in report.test_tamper[:EVIDENCE_MAX_PATHS]],
        }
    return payload

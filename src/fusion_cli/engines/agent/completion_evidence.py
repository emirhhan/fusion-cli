"""Kanıt özetinin sürümlü ve sınırlandırılmış istemci projeksiyonu."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .turn_report import TurnReport


#: Kits'e giden kanıt özetindeki liste tavanları (protokol satırı küçük kalır).
EVIDENCE_MAX_PATHS = 50
EVIDENCE_MAX_PROBLEMS = 10


def evidence_payload(report: TurnReport | None) -> dict[str, object] | None:
    """Tur raporunun Kits gibi istemcilere giden yapılandırılmış kanıt özeti.

    Kits `fusion_run` sonucunda yalnız metni görüyordu: "testler geçti" diyen ama
    kanıtı olmayan bir tur başarılı gibi sunulabiliyordu. `None`: rapor yok (sohbet).
    """
    if report is None:
        return None
    problems = [item.problem for item in report.job_deliveries if item.problem]
    if report.gate is not None and not report.gate.ok:
        problems.extend(report.gate.findings)
    payload: dict[str, object] = {
        "schema_version": 1,
        "dogrulandi": report.is_verified,
        "engelliyor": report.blocks_success,
        "yanlis_iddia": report.false_claim,
        "degisen": list(report.changed_paths[:EVIDENCE_MAX_PATHS]),
        "degisen_sayisi": len(report.changed_paths),
        "degisen_kisaltildi": len(report.changed_paths) > EVIDENCE_MAX_PATHS,
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

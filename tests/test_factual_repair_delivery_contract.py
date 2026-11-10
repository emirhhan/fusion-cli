"""Olgusal onarım talimatı teslim kapsamını ve kaynak yetkisini korur."""

from __future__ import annotations

import pytest

from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheckKind
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.loop_contract import _verification_correction_task


def _factual_failure() -> VerificationResult:
    summary = "Kaynaklarla uyuşmayan olgusal iddialar var."
    return VerificationResult(
        False,
        summary=summary,
        findings=("answer:9: Okunan kaynaklarda bu yapılandırma bayrağı bulunamadı.",),
        evidence=(
            CriterionEvidence(
                "research_grounding", VerificationCheckKind.TOOL, EvidenceStatus.FAILED, summary
            ),
        ),
    )


@pytest.mark.parametrize(
    "required_instruction",
    [
        "güncellenmiş raporun tamamını tek yanıtta sun",
        "değişmeyen bölümleri de koru",
        "yalnız değişen bölümleri veya değişiklik özeti verme",
        "Yalnız kullanıcının izin verdiği kaynak kapsamı içinde",
    ],
)
def test_factual_repair_preserves_whole_text_delivery_and_source_scope(
    required_instruction: str,
) -> None:
    """Bölüm yaması, teslim edilecek tam raporun yerine geçmemelidir."""
    correction = _verification_correction_task(_factual_failure())

    assert required_instruction in correction
    assert "answer:9" in correction
    assert "en az bir gerçek değiştirici araç" not in correction


def test_nonfactual_repair_keeps_existing_code_mutation_contract() -> None:
    correction = _verification_correction_task(
        VerificationResult(False, summary="Sözdizimi hatası", findings=("main.py:4",))
    )

    assert "en az bir gerçek değiştirici araç" in correction
    assert "güncellenmiş raporun tamamını" not in correction

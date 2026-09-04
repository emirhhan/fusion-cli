"""Profesyonel yürütme değerlendirmesinin güvenlik metrikleri."""

from __future__ import annotations

from evals.professional_execution import (
    ProfessionalExecutionMetrics,
    ProfessionalExecutionTrace,
    score_professional_execution,
)


def test_kabul_kapisi_kirilan_tamamlanmayi_false_success_sayar():
    metrics = score_professional_execution(
        ProfessionalExecutionTrace(
            reported_completed=True,
            acceptance_ok=False,
            model_calls=4,
            tool_calls=3,
            elapsed_s=1.5,
        )
    )

    assert metrics.acceptance_ok is False
    assert metrics.false_successes == 1


def test_yikici_adimda_kor_retry_ayri_olculur():
    metrics = score_professional_execution(
        ProfessionalExecutionTrace(
            reported_completed=False,
            acceptance_ok=False,
            retried_step_ids=("push",),
            retry_safe_step_ids=(),
            completed_step_ids=("inspect", "inspect"),
            model_calls=6,
            tool_calls=5,
            elapsed_s=2.0,
        )
    )

    assert metrics.blind_retries == 1
    assert metrics.repeated_completed_steps == 1


def test_bos_iz_sifir_metrik_uretir():
    metrics = score_professional_execution(ProfessionalExecutionTrace())

    assert metrics == ProfessionalExecutionMetrics()

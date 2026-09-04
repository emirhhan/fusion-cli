"""Hata sınıflandırma ve güvenli kurtarma karar matrisi."""

from __future__ import annotations

from fusion_cli.core.execution_plan import PlanStep, RetrySafety
from fusion_cli.core.failure import FailureCategory, RecoveryAction
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.recovery import (
    choose_recovery,
    classify_failure,
)
from fusion_cli.engines.agent.step_verification import StepVerificationResult


def _step(safety: RetrySafety) -> PlanStep:
    return PlanStep(
        step_id="publish",
        goal="yayınla",
        depends_on=(),
        expected_effects=("git_push",),
        allowed_tool_families=("shell",),
        success_criteria=("uzak durum doğrulandı",),
        verification_hint="uzak HEAD'i oku",
        retry_safety=safety,
    )


def test_zaman_asimi_siniflandirilir():
    failure = classify_failure(
        AgentOutcome(final_text="istek zaman aşımına uğradı", messages=[], ok=False),
        StepVerificationResult(ok=False),
    )

    assert failure.category is FailureCategory.TIMEOUT


def test_dogrulama_bulgusu_plan_onarimi_ister():
    failure = classify_failure(
        AgentOutcome(final_text="tamam", messages=[]),
        StepVerificationResult(ok=False, findings=("pytest kırıldı",)),
    )

    decision = choose_recovery(failure, _step(RetrySafety.SAFE), attempts=1)

    assert decision.action is RecoveryAction.REPLAN


def test_yikici_adim_otomatik_tekrar_almaz():
    failure = classify_failure(
        AgentOutcome(final_text="timeout", messages=[], ok=False),
        StepVerificationResult(ok=False),
    )

    decision = choose_recovery(failure, _step(RetrySafety.NEVER), attempts=1)

    assert decision.action is RecoveryAction.PAUSE


def test_dis_durum_once_gozlenir():
    failure = classify_failure(
        AgentOutcome(final_text="geçici bağlantı hatası", messages=[], ok=False),
        StepVerificationResult(ok=False),
    )

    decision = choose_recovery(failure, _step(RetrySafety.OBSERVE_FIRST), attempts=1)

    assert decision.action is RecoveryAction.OBSERVE


def test_ikinci_basarisizliktan_sonra_duraklatilir():
    failure = classify_failure(
        AgentOutcome(final_text="geçici bağlantı hatası", messages=[], ok=False),
        StepVerificationResult(ok=False),
    )

    decision = choose_recovery(failure, _step(RetrySafety.SAFE), attempts=2)

    assert decision.action is RecoveryAction.PAUSE

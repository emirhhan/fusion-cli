"""Agent ve doğrulama kanıtlarından kör olmayan kurtarma kararı üretir."""

from __future__ import annotations

from ...core.execution_plan import PlanStep, RetrySafety
from ...core.failure import (
    FailureCategory,
    FailureRecord,
    RecoveryAction,
    RecoveryDecision,
)
from .step_verification import StepVerificationResult


def classify_failure(outcome: object, verification: StepVerificationResult) -> FailureRecord:
    """Agent sonucunu ve post-condition bulgularını deterministik sınıflandır."""
    final_text = str(getattr(outcome, "final_text", ""))
    failed_tools = int(getattr(outcome, "failed_tool_calls", 0))
    combined = " ".join((final_text, *verification.findings)).lower()

    if verification.findings and bool(getattr(outcome, "ok", True)):
        return FailureRecord(FailureCategory.VERIFICATION, " ".join(verification.findings))
    if any(marker in combined for marker in ("zaman aş", "timeout", "timed out")):
        return FailureRecord(FailureCategory.TIMEOUT, combined.strip())
    if any(
        marker in combined
        for marker in ("geçici", "temporary", "bağlantı", "connection", "429", "503")
    ):
        return FailureRecord(FailureCategory.TRANSIENT, combined.strip())
    if any(marker in combined for marker in ("onaylanmadı", "izin", "permission", "denied")):
        return FailureRecord(FailureCategory.PERMISSION, combined.strip())
    if failed_tools or any(
        marker in combined for marker in ("geçersiz argüman", "invalid argument", "şema")
    ):
        return FailureRecord(FailureCategory.TOOL_CONTRACT, combined.strip())
    if verification.findings:
        return FailureRecord(FailureCategory.VERIFICATION, " ".join(verification.findings))
    return FailureRecord(FailureCategory.UNKNOWN, combined.strip() or "bilinmeyen hata")


def choose_recovery(
    failure: FailureRecord,
    step: PlanStep,
    attempts: int,
) -> RecoveryDecision:
    """Hata sınıfı, retry güvenliği ve deneme sayısından güvenli eylemi seç."""
    if step.retry_safety is RetrySafety.NEVER:
        return RecoveryDecision(
            RecoveryAction.PAUSE,
            "Adım yinelendiğinde dış etkiyi çoğaltabilir.",
        )
    if attempts >= 2:
        return RecoveryDecision(
            RecoveryAction.PAUSE,
            "Sınırlı kurtarma hakkı tükendi.",
        )
    if failure.category is FailureCategory.PERMISSION:
        return RecoveryDecision(
            RecoveryAction.PAUSE,
            "İzin veya onay kısıtı otomatik yolla aşılamaz.",
        )
    if step.retry_safety is RetrySafety.OBSERVE_FIRST:
        return RecoveryDecision(
            RecoveryAction.OBSERVE,
            "Yinelenmeden önce dış durum gözlenmeli.",
            "Önce mevcut dış durumu salt-okunur araçlarla doğrula; etki zaten oluştuysa yineleme.",
        )
    if failure.category in {FailureCategory.TIMEOUT, FailureCategory.TRANSIENT}:
        return RecoveryDecision(
            RecoveryAction.RETRY,
            "Geçici hata güvenli bir sınırlı yeniden denemeye uygun.",
            "Aynı hedefi koru; geçici hatadan sonra yalnızca bir kez yeniden dene.",
        )
    if failure.category in {FailureCategory.VERIFICATION, FailureCategory.TOOL_CONTRACT}:
        return RecoveryDecision(
            RecoveryAction.REPLAN,
            "Mevcut yaklaşımın veya araç argümanlarının düzeltilmesi gerekiyor.",
            f"Yaklaşımı dar biçimde onar. Önceki hata: {failure.detail[:1200]}",
        )
    return RecoveryDecision(
        RecoveryAction.PAUSE,
        "Bilinmeyen hata kör yeniden denemeye uygun değil.",
    )

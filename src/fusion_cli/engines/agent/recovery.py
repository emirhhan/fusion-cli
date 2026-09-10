"""Agent ve doğrulama kanıtlarından kör olmayan kurtarma kararı üretir."""

from __future__ import annotations

from pathlib import Path

from ...core.assets import is_asset_inventory
from ...core.diagnosis import diagnose
from ...core.evidence import EvidenceStatus
from ...core.execution_plan import PlanPhase, PlanStep, RetrySafety, VerificationCheckKind
from ...core.failure import (
    FailureCategory,
    FailureRecord,
    RecoveryAction,
    RecoveryDecision,
)
from .step_verification import StepVerificationResult, evaluate_file_check


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


#: Kör tekrarın tanındığı deneme sayısı.
#
# İkinci denemeden sonra hata sınıfı aynıysa üçüncüsü de aynı duvara çarpar; hak
# bütçeye değil BİLGİYE bağlıdır.
BASE_ATTEMPTS = 2

#: Doğrulama hatasında, yönerge yeni bilgi taşıdığında tanınan tavan.
#
# Ölçüldü (7 Eylül canlı Godot koşusu): ikinci denemenin bulgusu ilkinden farklıydı
# (dosyanın gerçek yeri bulunmuştu) ama hak zaten bitmişti. Bir hak daha vermek
# kör tekrar değildir: yönerge değiştiyse deneme de değişir.
MAX_VERIFICATION_ATTEMPTS = 3

#: Yeni bilgi kuralının geçerli olduğu hata sınıfları — yönergesi bulgudan üretilenler.
_REPAIRABLE = frozenset({FailureCategory.VERIFICATION, FailureCategory.TOOL_CONTRACT})


def _repair_guidance(failure: FailureRecord) -> str:
    """Bulgudan, KONUMU ve belirtiyi önce söyleyen onarım yönergesi üret.

    Ham hata metnini kopyalamak yetmiyor (ölçüldü, 5 Eylül Godot koşusu): elde
    `at: GDScript::reload (res://player.gd:12)` varken model aynı yanlışı
    tekrarladı. Tanı çıkarılabiliyorsa yönerge KONUMU ve BELİRTİYİ önce söyler.
    """
    tani = diagnose(failure.detail)
    onek = f"{tani.as_guidance()} " if tani is not None else ""
    return f"{onek}Yaklaşımı dar biçimde onar. Önceki hata: {failure.detail[:1200]}"


def choose_recovery(
    failure: FailureRecord,
    step: PlanStep,
    attempts: int,
    *,
    previous_guidance: str = "",
) -> RecoveryDecision:
    """Hata sınıfı, retry güvenliği ve deneme sayısından güvenli eylemi seç.

    `previous_guidance`, bir önceki denemeye verilen yönergedir: onarım yönergesi
    değişmediyse yeni deneme kör tekrardır ve hak verilmez.
    """
    if step.retry_safety is RetrySafety.NEVER:
        return RecoveryDecision(
            RecoveryAction.PAUSE,
            "Adım yinelendiğinde dış etkiyi çoğaltabilir.",
        )
    if failure.category is FailureCategory.PERMISSION:
        return RecoveryDecision(
            RecoveryAction.PAUSE,
            "İzin veya onay kısıtı otomatik yolla aşılamaz.",
        )
    if failure.category in _REPAIRABLE and step.retry_safety is not RetrySafety.OBSERVE_FIRST:
        guidance = _repair_guidance(failure)
        if attempts >= MAX_VERIFICATION_ATTEMPTS or (
            attempts >= BASE_ATTEMPTS and guidance == previous_guidance
        ):
            return RecoveryDecision(RecoveryAction.PAUSE, "Sınırlı kurtarma hakkı tükendi.")
        return RecoveryDecision(
            RecoveryAction.REPLAN,
            "Mevcut yaklaşımın veya araç argümanlarının düzeltilmesi gerekiyor.",
            guidance,
        )
    if attempts >= BASE_ATTEMPTS:
        return RecoveryDecision(
            RecoveryAction.PAUSE,
            "Sınırlı kurtarma hakkı tükendi.",
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
    return RecoveryDecision(
        RecoveryAction.PAUSE,
        "Bilinmeyen hata kör yeniden denemeye uygun değil.",
    )


def can_repair_local_inventory(step: PlanStep, root: Path) -> bool:
    """Allow one observed inventory repair only within a local file contract."""
    if (
        step.retry_safety is not RetrySafety.OBSERVE_FIRST
        or step.phase is PlanPhase.DISCOVERY
        or step.revision != 0
        or not step.expected_effects
        or not set(step.allowed_tool_families) <= {"files", "web"}
        or any(not effect.startswith("file:") for effect in step.expected_effects)
    ):
        return False
    try:
        resolved = root.resolve()
        if any(
            not (root / effect.removeprefix("file:")).resolve().is_relative_to(resolved)
            for effect in step.expected_effects
        ):
            return False
        return any(
            check.kind is VerificationCheckKind.FILE_EXISTS
            and is_asset_inventory(Path(check.target))
            and (root / check.target).resolve().is_relative_to(resolved)
            and evaluate_file_check(check, root).status is EvidenceStatus.FAILED
            for check in step.verification_checks
        )
    except (OSError, ValueError, RuntimeError):
        return False

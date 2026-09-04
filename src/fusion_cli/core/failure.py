"""Workflow başarısızlıkları ve güvenli kurtarma eylemlerinin çekirdek tipleri."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureCategory(StrEnum):
    """Yürütme sırasında gözlenebilen başarısızlık sınıfları."""

    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    TOOL_CONTRACT = "tool_contract"
    VERIFICATION = "verification"
    PERMISSION = "permission"
    UNKNOWN = "unknown"


class RecoveryAction(StrEnum):
    """Bir başarısızlıktan sonra uygulanabilecek sınırlı eylem."""

    RETRY = "retry"
    OBSERVE = "observe"
    REPLAN = "replan"
    PAUSE = "pause"


@dataclass(frozen=True, slots=True)
class FailureRecord:
    """Sınıflandırılmış hata ve karar için kullanılacak kanıt."""

    category: FailureCategory
    detail: str


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    """Seçilen kurtarma eylemi ve alt-tura verilecek yönlendirme."""

    action: RecoveryAction
    reason: str
    guidance: str = ""

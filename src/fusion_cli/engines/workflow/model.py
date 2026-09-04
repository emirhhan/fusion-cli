"""Deterministik workflow veri modeli — aşamalar, bütçe ve sonuç.

Zor görevlerde serbest ReAct döngüsü güvenilmez ve maliyeti öngörülemez. Workflow
bunu sabit bir boru hattına oturtur: localize → plan → patch → verify → review.
Her aşama bir model çağrısı bütçesinden harcar; bütçe dolarsa akış durur (ücretsiz
modellerin oran sınırı için zorunlu kapı). Yalnızca BAŞARISIZ aşama tekrarlanır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, StrEnum


class Stage(Enum):
    """Workflow boru hattının aşamaları (sıralı)."""

    LOCALIZE = "localize"  # sorunun/değişikliğin yerini bul
    PLAN = "plan"  # minimum değişiklik planını çıkar
    PATCH = "patch"  # en küçük yamayı uygula
    VERIFY = "verify"  # syntax/lint/test çalıştır
    REVIEW = "review"  # diff'i gözden geçir


#: Varsayılan boru hattı sırası.
PIPELINE: tuple[Stage, ...] = (
    Stage.LOCALIZE,
    Stage.PLAN,
    Stage.PATCH,
    Stage.VERIFY,
    Stage.REVIEW,
)

#: Başarısız bir aşamanın en fazla kaç kez yeniden denendiği (yalnızca o aşama).
MAX_STAGE_RETRIES = 1


@dataclass(frozen=True, slots=True)
class Budget:
    """Tur başına sabit model-çağrısı bütçesi."""

    max_model_calls: int


class BudgetEnvelope(StrEnum):
    """Profesyonel workflow içinde birbirinden bağımsız harcama alanları."""

    PLANNING = "planning"
    PER_STEP = "per_step"
    RECOVERY = "recovery"
    FINAL = "final_verification"


@dataclass(frozen=True, slots=True)
class WorkflowBudget:
    """Planlama, adım, kurtarma ve final kapısı için ayrı çağrı sınırları."""

    planning: int = 2
    per_step: int = 8
    recovery: int = 2
    final: int = 2

    def limit_for(self, envelope: BudgetEnvelope) -> int:
        """İstenen zarfın çağrı sınırını döndür."""
        return {
            BudgetEnvelope.PLANNING: self.planning,
            BudgetEnvelope.PER_STEP: self.per_step,
            BudgetEnvelope.RECOVERY: self.recovery,
            BudgetEnvelope.FINAL: self.final,
        }[envelope]


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    """Bir harcamanın kabul edilip edilmediği ve kalan hak."""

    allowed: bool
    remaining: int


class BudgetLedger:
    """Reddedilen harcamayı işlemeyen deterministik zarf sayacı."""

    def __init__(self, budget: WorkflowBudget) -> None:
        self._budget = budget
        self._used = dict.fromkeys(BudgetEnvelope, 0)

    def charge(self, envelope: BudgetEnvelope, calls: int) -> BudgetDecision:
        """Pozitif çağrı harcamasını zarf sığıyorsa işle."""
        if calls < 0:
            raise ValueError("Workflow çağrı harcaması negatif olamaz.")
        limit = self._budget.limit_for(envelope)
        candidate = self._used[envelope] + calls
        if candidate > limit:
            return BudgetDecision(False, max(0, limit - self._used[envelope]))
        self._used[envelope] = candidate
        return BudgetDecision(True, limit - candidate)

    def used(self, envelope: BudgetEnvelope) -> int:
        """Bir zarfta işlenmiş çağrı sayısını döndür."""
        return self._used[envelope]


@dataclass(frozen=True, slots=True)
class StageOutcome:
    """Tek bir aşama çalıştırmasının sonucu."""

    ok: bool
    #: Bu aşamanın harcadığı model çağrısı sayısı (bütçeden düşülür).
    model_calls: int
    #: Sonraki aşamalara aktarılacak kısa not (bulgu/plan/yamalanan yer…).
    note: str = ""


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Tüm workflow çalıştırmasının sonucu."""

    ok: bool
    stages_run: tuple[Stage, ...] = field(default_factory=tuple)
    model_calls: int = 0
    #: Bütçe dolduğu için mi durdu.
    budget_exhausted: bool = False
    summary: str = ""
    #: Son anlamlı aşama notu (kullanıcıya gösterilecek asıl sonuç/özet).
    final_note: str = ""

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
    per_step: int = 24
    recovery: int = 12
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


#: Adım kapsamında sayılan zarflar (bkz. `BudgetLedger._key`).
_SCOPED_ENVELOPES = frozenset({BudgetEnvelope.PER_STEP, BudgetEnvelope.RECOVERY})


class BudgetLedger:
    """Reddedilen harcamayı işlemeyen deterministik zarf sayacı."""

    def __init__(self, budget: WorkflowBudget) -> None:
        self._budget = budget
        self._used: dict[tuple[BudgetEnvelope, str], int] = {}

    def _key(self, envelope: BudgetEnvelope, scope: str) -> tuple[BudgetEnvelope, str]:
        """Zarfın sayaç anahtarını üret.

        `PER_STEP` ve `RECOVERY` ADIM BAŞINA sayılır — tasarımın adlandırması da
        budur ("adım yürütme", "adım kurtarma"). Ölçüldü (Godot koşusu): tek sayaç
        kullanıldığında dört adımlık planın ilk adımı bütün hakkı harcadı ve kalan
        üç adım hiç başlayamadan workflow duraklatıldı; üçüncü-parti bir MCP'nin
        tek hatası da tüm planın onarım hakkını tüketti.

        `PLANNING` ve `FINAL` plan başına TEK haktır ve kapsam almaz.

        Kör tekrar bu sayaçla değil hata sınıflandırması ve `retry_safety` ile
        engellenir; adım başına hak vermek o kapıyı zayıflatmaz.
        """
        return (envelope, scope if envelope in _SCOPED_ENVELOPES else "")

    def charge(
        self, envelope: BudgetEnvelope, calls: int, *, scope: str = ""
    ) -> BudgetDecision:
        """Pozitif çağrı harcamasını zarf sığıyorsa işle."""
        if calls < 0:
            raise ValueError("Workflow çağrı harcaması negatif olamaz.")
        limit = self._budget.limit_for(envelope)
        key = self._key(envelope, scope)
        used = self._used.get(key, 0)
        candidate = used + calls
        if candidate > limit:
            return BudgetDecision(False, max(0, limit - used))
        self._used[key] = candidate
        return BudgetDecision(True, limit - candidate)

    def used(self, envelope: BudgetEnvelope, *, scope: str = "") -> int:
        """Bir zarfta (gerekirse belirtilen adım kapsamında) işlenmiş çağrı sayısı."""
        return self._used.get(self._key(envelope, scope), 0)


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

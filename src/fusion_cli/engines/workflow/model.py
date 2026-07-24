"""Deterministik workflow veri modeli — aşamalar, bütçe ve sonuç.

Zor görevlerde serbest ReAct döngüsü güvenilmez ve maliyeti öngörülemez. Workflow
bunu sabit bir boru hattına oturtur: localize → plan → patch → verify → review.
Her aşama bir model çağrısı bütçesinden harcar; bütçe dolarsa akış durur (ücretsiz
modellerin oran sınırı için zorunlu kapı). Yalnızca BAŞARISIZ aşama tekrarlanır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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

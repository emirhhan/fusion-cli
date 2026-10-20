"""Kazanan seçimi — saf, regresyon korumalı.

Bir temel (baseline) prompt ile birkaç aday varyantın eval raporlarını alır; kazananı
şu iki koşulla seçer:

1. **Regresyon yok** — aday, eskiden geçen hiçbir görevi bozmamış olmalı (Faz 0
   `compare_reports` ile). Bir görevi kırarak toplam skoru yükselten aday elenir.
2. **Ölçülebilir iyileşme** — aday `task_success_rate`'i en az `min_improvement`
   kadar yükseltmeli. Hiçbir aday geçmezse temel korunur (yayım yok).
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.compare import compare_reports
from evals.metrics import RunReport

from .variants import PromptVariant

#: Yeni sürümün yayımlanması için gereken asgari başarı oranı artışı.
DEFAULT_MIN_IMPROVEMENT = 0.02


@dataclass(frozen=True, slots=True)
class Candidate:
    """Bir prompt varyantı ve onun eval raporu."""

    variant: PromptVariant
    report: RunReport


@dataclass(frozen=True, slots=True)
class Selection:
    """Seçim sonucu: kazanan varyant, iyileşti mi ve gerekçe."""

    winner: PromptVariant
    improved: bool
    reason: str


def select_winner(
    baseline: Candidate,
    candidates: tuple[Candidate, ...],
    *,
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
) -> Selection:
    """Regresyonsuz ve en çok iyileştiren adayı seç; hiçbiri geçmezse temeli koru."""

    best: Candidate | None = None
    best_delta = 0.0
    for candidate in candidates:
        comparison = compare_reports(baseline.report, candidate.report)
        if comparison.regressions:
            continue
        delta = candidate.report.task_success_rate - baseline.report.task_success_rate
        if delta >= min_improvement and delta > best_delta:
            best = candidate
            best_delta = delta

    if best is None:
        return Selection(
            winner=baseline.variant,
            improved=False,
            reason="regresyonsuz ve yeterince iyileştiren aday yok; temel korundu",
        )
    return Selection(
        winner=best.variant,
        improved=True,
        reason=f"başarı oranı +{best_delta:.3f} (regresyonsuz)",
    )

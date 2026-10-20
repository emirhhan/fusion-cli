"""Offline optimizasyon döngüsü — üret, ölç, seç, yayımla.

Varyant üretimi ve değerlendirme (eval setinde çalıştırma) birer protokolün
arkasındadır: gerçek uygulama model çağırır ya da agent'ı koşturur, ama seçim/
sürümleme mantığı bu bağımlılıklar mock'lanarak ağsız test edilir.

Akış: temel promptu değerlendir → n varyant üret → her birini değerlendir →
regresyonsuz en iyi adayı seç → yalnızca iyileşme varsa yeni sürümü yayımla.
"""

from __future__ import annotations

from typing import Protocol

from evals.metrics import RunReport

from .selection import DEFAULT_MIN_IMPROVEMENT, Candidate, Selection, select_winner
from .variants import PromptVariant
from .versioning import PromptStore

#: Bir turda üretilecek varsayılan varyant sayısı.
DEFAULT_VARIANT_COUNT = 3


class VariantGenerator(Protocol):
    """Temel bir prompttan alternatif metinler üreten taraf (ör. bir model)."""

    async def generate(self, base_text: str, count: int) -> tuple[str, ...]: ...


class PromptEvaluator(Protocol):
    """Bir promptu eval setinde çalıştırıp rapor döndüren taraf."""

    async def evaluate(self, prompt_text: str) -> RunReport: ...


async def optimize(
    name: str,
    base_text: str,
    *,
    generator: VariantGenerator,
    evaluator: PromptEvaluator,
    store: PromptStore,
    variant_count: int = DEFAULT_VARIANT_COUNT,
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
) -> Selection:
    """Promptu offline optimize et. İyileşme varsa yeni sürümü yayımlar."""

    current = store.current(name)
    base_version = current.version if current is not None else 0
    baseline = Candidate(
        variant=PromptVariant(name=name, text=base_text, version=base_version),
        report=await evaluator.evaluate(base_text),
    )

    texts = await generator.generate(base_text, variant_count)
    candidates = tuple(
        [
            Candidate(
                variant=PromptVariant(name=name, text=text),
                report=await evaluator.evaluate(text),
            )
            for text in texts
        ]
    )

    selection = select_winner(baseline, candidates, min_improvement=min_improvement)
    if selection.improved:
        published = store.publish(name, selection.winner.text)
        return Selection(winner=published, improved=True, reason=selection.reason)
    return selection

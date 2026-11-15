"""Offline optimizasyon döngüsü — üret, ölç, seç, yayımla.

Varyant üretimi ve değerlendirme (eval setinde çalıştırma) birer protokolün
arkasındadır: gerçek uygulama model çağırır ya da agent'ı koşturur, ama seçim/
sürümleme mantığı bu bağımlılıklar mock'lanarak ağsız test edilir.

Akış: temel promptu değerlendir → n varyant üret → her birini değerlendir →
regresyonsuz en iyi adayı seç → yalnızca iyileşme varsa yeni sürümü yayımla.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from evals.metrics import RunReport

from .research_comparison import compare_pair
from .research_evidence import RunEvidence, check_variant_count
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


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Arama sonucu: temel, ölçülen adaylar ve seçim. Hiçbir şey yayımlanmamıştır."""

    baseline: Candidate
    candidates: tuple[Candidate, ...]
    selection: Selection
    manifest: tuple[RunEvidence, ...] = ()

    @property
    def winner_report(self) -> RunReport | None:
        """Seçilen adayın raporu; iyileşme yoksa `None`."""
        if not self.selection.improved:
            return None
        return next(
            (c.report for c in self.candidates if c.variant.text == self.selection.winner.text),
            None,
        )


async def search(
    name: str,
    base_text: str,
    *,
    generator: VariantGenerator,
    evaluator: PromptEvaluator,
    base_version: int = 0,
    baseline_report: RunReport | None = None,
    variant_count: int = DEFAULT_VARIANT_COUNT,
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
) -> SearchResult:
    """Temeli ve adayları ölç, regresyonsuz en iyisini seç. YAYIMLAMAZ.

    `baseline_report` yalnız teşhistir; her aday bağımsız AB/BA çiftleriyle ölçülür.
    """

    check_variant_count(variant_count)
    baseline = Candidate(
        PromptVariant(name=name, text=base_text, version=base_version),
        baseline_report if baseline_report is not None else await evaluator.evaluate(base_text),
    )
    texts = await generator.generate(base_text, variant_count)
    if len(texts) > variant_count:
        raise ValueError("üretici istenenden fazla aday döndürdü; tur durduruldu")
    candidates: list[Candidate] = []
    manifest: list[RunEvidence] = []
    for text in texts:
        paired = await compare_pair(evaluator, base_text, text, stage="development")
        offset = len(manifest)
        manifest.extend(replace(item, order=offset + item.order) for item in paired.manifest)
        if paired.problem:
            continue
        candidate = Candidate(
            PromptVariant(name=name, text=text), paired.candidate, paired.baseline
        )
        local = select_winner(
            Candidate(baseline.variant, paired.baseline),
            (candidate,),
            min_improvement=min_improvement,
        )
        if local.improved:
            candidates.append(candidate)
    selection = select_winner(baseline, tuple(candidates), min_improvement=min_improvement)
    return SearchResult(baseline, tuple(candidates), selection, tuple(manifest))


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
    result = await search(
        name,
        base_text,
        generator=generator,
        evaluator=evaluator,
        base_version=current.version if current is not None else 0,
        variant_count=variant_count,
        min_improvement=min_improvement,
    )
    if result.selection.improved:
        published = store.publish(name, result.selection.winner.text)
        return Selection(winner=published, improved=True, reason=result.selection.reason)
    return result.selection

"""İki çalıştırma raporunu diff'leyen saf karşılaştırma.

Sonraki her faz "eski vs yeni" olarak ölçülür: metrik deltaları ve görev bazında
başarı değişimleri (gerileme/iyileşme) çıkarılır.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.metrics import RunReport


@dataclass(frozen=True, slots=True)
class MetricDelta:
    """Tek bir özet metriğin eski/yeni değeri ve farkı."""

    name: str
    baseline: float
    candidate: float

    @property
    def delta(self) -> float:
        return self.candidate - self.baseline


@dataclass(frozen=True, slots=True)
class RunComparison:
    """İki raporun karşılaştırması: metrik deltaları + başarı değişimleri."""

    metrics: tuple[MetricDelta, ...]
    #: Eskiden başarılıyken yenide başarısızlaşan görev kimlikleri.
    regressions: tuple[str, ...]
    #: Eskiden başarısızken yenide başarılı olan görev kimlikleri.
    improvements: tuple[str, ...]


def _metric_deltas(baseline: RunReport, candidate: RunReport) -> tuple[MetricDelta, ...]:
    names_and_values = [
        ("task_success_rate", baseline.task_success_rate, candidate.task_success_rate),
        (
            "first_attempt_success_rate",
            baseline.first_attempt_success_rate,
            candidate.first_attempt_success_rate,
        ),
        ("total_retries", float(baseline.total_retries), float(candidate.total_retries)),
        ("mean_model_calls", baseline.mean_model_calls, candidate.mean_model_calls),
        ("mean_duration_seconds", baseline.mean_duration_seconds, candidate.mean_duration_seconds),
    ]
    return tuple(
        MetricDelta(name=name, baseline=base, candidate=cand)
        for name, base, cand in names_and_values
    )


def compare_reports(baseline: RunReport, candidate: RunReport) -> RunComparison:
    """Eski (baseline) ve yeni (candidate) raporu karşılaştırır.

    Görev bazında değişim, yalnızca iki raporda da bulunan görev kimlikleri için
    hesaplanır; yalnızca bir tarafta olan görevler değişim listelerine girmez.
    """

    baseline_success = {r.task_id: r.success for r in baseline.results}
    candidate_success = {r.task_id: r.success for r in candidate.results}
    shared_ids = [task_id for task_id in baseline_success if task_id in candidate_success]

    regressions = tuple(
        task_id
        for task_id in shared_ids
        if baseline_success[task_id] and not candidate_success[task_id]
    )
    improvements = tuple(
        task_id
        for task_id in shared_ids
        if not baseline_success[task_id] and candidate_success[task_id]
    )
    return RunComparison(
        metrics=_metric_deltas(baseline, candidate),
        regressions=regressions,
        improvements=improvements,
    )

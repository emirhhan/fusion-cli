"""Mevcut değerlendirici üzerinde bağımsız AB ve BA karşılaştırmaları."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from evals.compare import compare_reports
from evals.metrics import RunReport, merge_runs

from .proposals import text_digest
from .research_evidence import RunEvidence, measure, safety_problem, served_model_problem


class Evaluator(Protocol):
    """Mevcut rapor üreten değerlendirme sözleşmesi."""

    async def evaluate(self, prompt_text: str) -> RunReport: ...


@dataclass(frozen=True, slots=True)
class PairedComparison:
    """Aynı görev, tekrar, model ve bütçeyle iki bağımsız sıra."""

    baseline: RunReport
    candidate: RunReport
    manifest: tuple[RunEvidence, ...]
    problem: str


def _combine(first: RunReport, second: RunReport) -> RunReport:
    by_id = {result.task_id: result for result in second.results}
    if {result.task_id for result in first.results} != set(by_id):
        raise ValueError("AB/BA koşularında aynı görev kimlikleri ölçülmeli")
    return RunReport(
        tuple(
            replace(
                merge_runs([result, by_id[result.task_id]]),
                runs=result.runs + by_id[result.task_id].runs,
                passes=result.passes + by_id[result.task_id].passes,
            )
            for result in first.results
        ),
        metadata=(
            replace(
                first.metadata,
                calls=first.metadata.calls + second.metadata.calls,
                repeat=first.metadata.repeat + second.metadata.repeat,
                model_calls_total=(
                    first.metadata.model_calls_total + second.metadata.model_calls_total
                    if first.metadata.model_calls_total is not None
                    and second.metadata.model_calls_total is not None
                    else None
                ),
            )
            if first.metadata is not None and second.metadata is not None
            else None
        ),
    )


def _pair_problem(base: RunReport, candidate: RunReport) -> str:
    if {result.task_id for result in base.results} != {
        result.task_id for result in candidate.results
    }:
        return "karşılaştırma görev kimlikleri değişti; ölçüm güvenilirliği düştü"
    if base.metadata is not None and candidate.metadata is not None:
        for field in (
            "profile",
            "model",
            "requested_model",
            "arm",
            "repeat",
            "split",
            "split_digest",
            "source_digest",
            "scorer_digest",
            "task_budgets",
            "effective_config_digest",
            "max_model_calls",
            "timeout_s",
            "initial_workspace_digest",
        ):
            if getattr(base.metadata, field) != getattr(candidate.metadata, field):
                return f"karşılaştırma kolunun koşulu değişti: {field}"
    problem = served_model_problem(base, candidate) or safety_problem(base, candidate)
    if problem:
        return problem
    regressions = compare_reports(base, candidate).regressions
    if regressions:
        return f"karşılaştırmada eskiden geçen görev bozuldu: {', '.join(regressions)}"
    if candidate.task_success_rate < base.task_success_rate:
        return "karşılaştırmada başarı oranı düştü"
    return ""


async def compare_pair(
    evaluator: Evaluator, base_text: str, candidate_text: str, *, stage: str
) -> PairedComparison:
    """AB ve BA sırasını gerçekten koştur; teşhis raporunu tekrar kullanma."""
    reports: list[RunReport] = []
    manifest: list[RunEvidence] = []
    for order, (arm, text) in enumerate(
        (("A", base_text), ("B", candidate_text), ("B", candidate_text), ("A", base_text)),
        start=1,
    ):
        report = await evaluator.evaluate(text)
        reports.append(report)
        manifest.append(
            RunEvidence(stage, arm, order, text_digest(text), measure(report), report.metadata)
        )
    problems = (_pair_problem(reports[0], reports[1]), _pair_problem(reports[3], reports[2]))
    return PairedComparison(
        _combine(reports[0], reports[3]),
        _combine(reports[1], reports[2]),
        tuple(manifest),
        next((problem for problem in problems if problem), ""),
    )

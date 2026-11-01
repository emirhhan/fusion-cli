"""İstem seçiminin ölçülmüş maliyeti ve sır taşımayan koşu kanıtı."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from evals.metrics import RunReport
from evals.profiles import RunMetadata

from fusion_cli.core.events import ToolExecuted, ToolOutcome

MAX_VARIANT_COUNT = 4


def check_variant_count(count: int) -> None:
    """Yanlış aday sayısını herhangi bir dış çağrıdan önce reddet."""
    if type(count) is not int or not 1 <= count <= MAX_VARIANT_COUNT:
        raise ValueError(f"aday sayısı 1 ile {MAX_VARIANT_COUNT} arasında olmalı")


@dataclass(frozen=True, slots=True)
class Measurement:
    """USD bilinmiyorsa None; çağrı sayısı parasal maliyet değildir."""

    model_calls: int | None
    cost_usd: float | None
    failed_mutations: int | None
    unknowns: tuple[str, ...]


def measure(report: RunReport) -> Measurement:
    """Gerçek çağrı kimlikleri ve başarısız değiştirici araç olaylarını topla."""
    model_calls = report.metadata.model_calls_total if report.metadata else None
    if model_calls is None and all(result.runs == 1 for result in report.results):
        model_calls = sum(result.model_calls for result in report.results)
    calls = report.metadata.calls if report.metadata else ()
    known_costs = [call.cost_usd for call in calls if call.cost_usd is not None]
    is_cost_known = (
        bool(calls)
        and len(known_costs) == len(calls)
        and len(calls) == model_calls
        and all(isfinite(cost) and cost >= 0 for cost in known_costs)
    )
    events = tuple(event for result in report.results for event in result.trace_events)
    tools = tuple(event for event in events if isinstance(event, ToolExecuted))
    failed = sum(event.outcome is ToolOutcome.FAILED and event.mutating is True for event in tools)
    has_mutation_evidence = bool(tools) and all(event.mutating is not None for event in tools)
    return Measurement(
        model_calls=model_calls,
        cost_usd=sum(known_costs) if is_cost_known else None,
        failed_mutations=failed if has_mutation_evidence else None,
        unknowns=(() if model_calls is not None else ("model_calls",))
        + (() if is_cost_known else ("cost_usd",))
        + (() if has_mutation_evidence else ("failed_mutations",))
        + (() if calls and all(call.served_model for call in calls) else ("served_model",))
        + ("unauthorized_execution",),
    )


def safety_problem(base: RunReport, candidate: RunReport) -> str:
    """Ölçülebilen her kaynakta artışı reddet; eksik ölçümü sıfır sayma."""
    before, after = measure(base), measure(candidate)
    if before.model_calls is not None and (
        after.model_calls is None or after.model_calls > before.model_calls
    ):
        return "adayın model çağrısı maliyeti arttı veya ölçümü eksildi"
    if before.cost_usd is not None and (after.cost_usd is None or after.cost_usd > before.cost_usd):
        return "adayın USD maliyeti arttı veya ölçümü eksildi"
    if after.failed_mutations is not None and after.failed_mutations > (
        before.failed_mutations if before.failed_mutations is not None else 0
    ):
        return "adayın başarısız değiştirici araç yürütmesi arttı"
    if before.failed_mutations is not None and after.failed_mutations is None:
        return "adayın değiştirici araç yürütme ölçümü eksildi"
    if candidate.false_success_count > base.false_success_count:
        return "adayın yanlış başarı beyanı arttı"
    return ""


@dataclass(frozen=True, slots=True)
class RunEvidence:
    """Gerçekte çalıştırılan bir kolun sıra ve ölçüm kaydı."""

    stage: str
    arm: str
    order: int
    prompt_digest: str
    measurement: Measurement
    metadata: RunMetadata | None = None


def served_model_problem(base: RunReport, candidate: RunReport) -> str:
    """Aynı rolün bilinen sunulan modeli değişirse karşılaştırmayı reddet."""
    before = base.metadata.calls if base.metadata else ()
    after = candidate.metadata.calls if candidate.metadata else ()
    for role in {call.role for call in (*before, *after)}:
        known_before = {
            call.served_model for call in before if call.role == role and call.served_model
        }
        known_after = {
            call.served_model for call in after if call.role == role and call.served_model
        }
        if known_before and known_after and known_before != known_after:
            return f"karşılaştırma rolünün bilinen sunulan modeli değişti: {role}"
    return ""

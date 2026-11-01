"""Aday/terfi ve dış provider yaşam döngüsü olaylarından dürüst metrikler."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from fusion_cli.core.events import (
    AttemptExperimentFinished,
    CandidateFinished,
    CandidatePromoted,
    CandidateSelected,
    CandidateStarted,
    Event,
    ModelCallAbandoned,
    ModelCallFinished,
    ModelCallStarted,
    WorkspaceConflictDetected,
)
from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus, summarize_criteria


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    """Ana oranların birimi görev/tekrardır; step_* alanları ayrı adım tanılarıdır.

    pass@1 paydası supported_candidate_tasks, @2 paydası two_candidate_tasks olur.
    Desteklenmeyen görev içeren ana kohort oranları None kalır.
    """

    pass_at_1: float | None
    oracle_at_2: float | None
    selected_at_2: float | None
    serial_at_c: float | None
    candidate_tasks: int
    two_candidate_tasks: int
    lifecycle_calls: int
    abandoned_calls: int
    open_calls: int
    unknown_served_calls: int
    mismatched_model_calls: int
    source_conflicts: int
    rollback_conflicts: int
    supported_candidate_tasks: int = 0
    unsupported_candidate_tasks: int = 0
    unavailable_candidate_tasks: int = 0
    unavailable_serial_tasks: int = 0
    step_pass_at_1: float | None = None
    step_oracle_at_2: float | None = None
    step_selected_at_2: float | None = None
    candidate_steps: int = 0
    two_candidate_steps: int = 0


def accepted(ok: bool, criteria: tuple[CriterionEvidence, ...], required: tuple[str, ...]) -> bool:
    """Bütün gerekli koşulların uygulanabilir gerçek kanıtını iste."""
    measured = tuple(item for item in summarize_criteria(criteria) if item.applicable)
    present = {item.criterion_id for item in measured}
    return (
        ok
        and bool(required)
        and set(required) <= present
        and all(
            item.status is EvidenceStatus.PASSED
            for item in measured
            if item.criterion_id in required
        )
    )


@dataclass
class _CandidateStep:
    results: dict[int, bool] = field(default_factory=dict)
    whole_results: dict[int, bool] = field(default_factory=dict)
    ordinals: dict[str, int] = field(default_factory=dict)
    selected: str | None = None
    promoted: bool = False


@dataclass
class _CandidateTask:
    steps: dict[tuple[str, str], _CandidateStep] = field(default_factory=dict)
    final: AttemptExperimentFinished | None = None


def _rate(values: Sequence[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _candidate_tasks(events: Sequence[Event]) -> tuple[_CandidateTask, ...]:
    tasks: list[_CandidateTask] = []
    active: dict[tuple[str, int, str | None], _CandidateTask] = {}
    candidates: dict[str, _CandidateStep] = {}
    latest: dict[tuple[str | None, str, str], _CandidateStep] = {}
    for event in events:
        if isinstance(event, (CandidateStarted, AttemptExperimentFinished)):
            key = (event.task_id, event.repeat, event.turn_id)
            if key not in active or active[key].final is not None:
                active[key] = _CandidateTask()
                tasks.append(active[key])
            task = active[key]
            if isinstance(event, AttemptExperimentFinished):
                task.final = event
            elif event.candidate_id is not None:
                step = task.steps.setdefault((event.plan_id, event.step_id), _CandidateStep())
                step.ordinals[event.candidate_id] = event.ordinal
                candidates[event.candidate_id] = step
                latest[event.turn_id, event.plan_id, event.step_id] = step
        elif isinstance(event, CandidateFinished) and event.candidate_id in candidates:
            step = candidates[event.candidate_id]
            results = step.whole_results if event.scope == "task" else step.results
            results[event.ordinal] = accepted(event.ok, event.criteria, event.required_criteria)
        elif isinstance(event, CandidateSelected):
            selected = latest.get((event.turn_id, event.plan_id, event.step_id))
            if selected is not None:
                selected.selected = event.selected_candidate_id
        elif isinstance(event, CandidatePromoted) and event.candidate_id in candidates:
            step = candidates[event.candidate_id]
            step.promoted = event.candidate_id == step.selected and accepted(
                event.ok, event.criteria, event.required_criteria
            )
    return tuple(tasks)


def _task_rates(
    tasks: tuple[_CandidateTask, ...],
) -> tuple[float | None, float | None, float | None]:
    """Yalnız bağımsız tam görev kanıtı olan tek-adım denemelerini karşılaştır."""
    first: list[bool] = []
    oracle: list[bool] = []
    selected: list[bool] = []
    for task in tasks:
        if len(task.steps) != 1 or task.final is None:
            return None, None, None
        step = next(iter(task.steps.values()))
        if 1 not in step.whole_results:
            return None, None, None
        if 1 in step.whole_results:
            first.append(step.whole_results[1])
        if 1 in step.whole_results and 2 in step.whole_results:
            oracle.append(any(step.whole_results.values()))
            final = task.final
            chosen = step.whole_results.get(step.ordinals.get(step.selected or "", 0), False)
            selected.append(
                chosen
                and step.promoted
                and accepted(final.ok, final.criteria, final.required_criteria)
            )
    return _rate(first), _rate(oracle), _rate(selected)


def _identity_mismatch(event: ModelCallFinished, expected: dict[str, str]) -> bool:
    frozen = expected.get(event.candidate_id or "")
    requested = event.requested_model
    served = event.result.served_by
    return bool(
        (frozen and requested and frozen != requested)
        or (requested and served and requested != served)
    )


def _measured_candidates(tasks: tuple[_CandidateTask, ...]) -> list[_CandidateTask]:
    return [
        task
        for task in tasks
        if task.final is not None
        and task.final.arm == "candidates"
        and task.final.measurement == "measured"
    ]


def _whole_pair_count(tasks: Sequence[_CandidateTask]) -> int:
    return sum(
        len(task.steps) == 1
        and all(index in next(iter(task.steps.values())).whole_results for index in (1, 2))
        for task in tasks
    )


def reduce_candidate_metrics(events: Sequence[Event]) -> CandidateMetrics:
    """Lifecycle sayısı fiziksel ağ retry sayısı değildir; kimlikler dedupe edilir."""
    tasks = _candidate_tasks(events)
    measured = _measured_candidates(tasks)
    steps = [step for task in tasks for step in task.steps.values()]
    first = [step.results[1] for step in steps if 1 in step.results]
    pairs = [step for step in steps if 1 in step.results and 2 in step.results]
    task_rates = _task_rates(tuple(measured))
    serial = [
        accepted(event.ok, event.criteria, event.required_criteria)
        for event in events
        if isinstance(event, AttemptExperimentFinished)
        and event.arm == "serial"
        and event.measurement == "measured"
    ]
    lifecycle = _lifecycle_metrics(events)
    mismatches = lifecycle.mismatches
    return CandidateMetrics(
        None if mismatches else task_rates[0],
        None if mismatches else task_rates[1],
        None if mismatches else task_rates[2],
        None if mismatches else _rate(serial),
        len(measured),
        _whole_pair_count(measured),
        lifecycle.calls,
        lifecycle.abandoned,
        lifecycle.open_calls,
        lifecycle.unknown_served,
        lifecycle.mismatches,
        lifecycle.source_conflicts,
        lifecycle.rollback_conflicts,
        sum(
            len(task.steps) == 1 and 1 in next(iter(task.steps.values())).whole_results
            for task in measured
        ),
        sum(
            len(task.steps) != 1 or not next(iter(task.steps.values())).whole_results
            for task in measured
        ),
        sum(
            task.final is not None
            and task.final.arm == "candidates"
            and task.final.measurement == "unavailable"
            for task in tasks
        ),
        sum(
            isinstance(event, AttemptExperimentFinished)
            and event.arm == "serial"
            and event.measurement == "unavailable"
            for event in events
        ),
        _rate(first),
        _rate([any(step.results.values()) for step in pairs]),
        _rate([step.promoted for step in pairs]),
        len(first),
        len(pairs),
    )


@dataclass(frozen=True)
class _LifecycleMetrics:
    calls: int
    abandoned: int
    open_calls: int
    unknown_served: int
    mismatches: int
    source_conflicts: int
    rollback_conflicts: int


def _lifecycle_metrics(events: Sequence[Event]) -> _LifecycleMetrics:
    starts = {
        event.call_id for event in events if isinstance(event, ModelCallStarted) and event.call_id
    }
    finishes = {
        event.call_id: event
        for event in events
        if isinstance(event, ModelCallFinished) and event.call_id
    }
    abandoned = {
        event.call_id for event in events if isinstance(event, ModelCallAbandoned) and event.call_id
    }
    conflicts = [event for event in events if isinstance(event, WorkspaceConflictDetected)]
    expected = {
        event.candidate_id: event.requested_model
        for event in events
        if isinstance(event, CandidateStarted) and event.candidate_id is not None
    }
    mismatches = sum(_identity_mismatch(event, expected) for event in finishes.values())
    return _LifecycleMetrics(
        len(starts | finishes.keys() | abandoned),
        len(abandoned - finishes.keys()),
        len(starts - finishes.keys() - abandoned),
        sum(not event.result.served_by for event in finishes.values()),
        mismatches,
        sum(event.count for event in conflicts if event.phase == "source-promotion"),
        sum(event.count for event in conflicts if event.phase == "rollback"),
    )

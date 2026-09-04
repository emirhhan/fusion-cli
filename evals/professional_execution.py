"""Planlı yürütmenin yanlış başarı ve güvenli retry metrikleri."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProfessionalExecutionTrace:
    """Ağsız değerlendirme için workflow'dan alınmış minimal gözlem."""

    reported_completed: bool = False
    acceptance_ok: bool = False
    retried_step_ids: tuple[str, ...] = ()
    retry_safe_step_ids: tuple[str, ...] = ()
    completed_step_ids: tuple[str, ...] = ()
    model_calls: int = 0
    tool_calls: int = 0
    elapsed_s: float = 0.0


@dataclass(frozen=True, slots=True)
class ProfessionalExecutionMetrics:
    """Profesyonel yürütmenin ölçülebilir kabul ve emniyet özeti."""

    acceptance_ok: bool = False
    false_successes: int = 0
    blind_retries: int = 0
    repeated_completed_steps: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    elapsed_s: float = 0.0


def score_professional_execution(
    trace: ProfessionalExecutionTrace,
) -> ProfessionalExecutionMetrics:
    """İzden yanlış başarı, kör retry ve yinelenen tamamlanmış adımları ölç."""
    safe_retries = set(trace.retry_safe_step_ids)
    blind_retries = sum(step_id not in safe_retries for step_id in trace.retried_step_ids)
    unique_completed = set(trace.completed_step_ids)
    repeated_completed = len(trace.completed_step_ids) - len(unique_completed)
    return ProfessionalExecutionMetrics(
        acceptance_ok=trace.acceptance_ok,
        false_successes=int(trace.reported_completed and not trace.acceptance_ok),
        blind_retries=blind_retries,
        repeated_completed_steps=repeated_completed,
        model_calls=trace.model_calls,
        tool_calls=trace.tool_calls,
        elapsed_s=trace.elapsed_s,
    )

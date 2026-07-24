"""Görev sonuçları ve çalıştırma raporu — saf toplama.

Ham çalıştırma gözlemlerini (başarı ölçütüyle birlikte) tek görev sonucuna, görev
sonuçlarını da tüm çalıştırmayı özetleyen orana/ortalamaya çevirir. Hiçbir yan
etkisi yoktur; doğrudan test edilir.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.criteria import evaluate_criterion
from evals.execution import TaskExecution
from evals.tasks import EvalTask


@dataclass(frozen=True, slots=True)
class TaskResult:
    """Tek bir görevin puanlanmış sonucu."""

    task_id: str
    success: bool
    #: Görev başarılı VE hiç yeniden deneme yapılmadan bittiyse doğru.
    first_attempt_success: bool
    retries: int
    model_calls: int
    duration_seconds: float


def score_task(task: EvalTask, execution: TaskExecution) -> TaskResult:
    """Bir görevi, ölçütü ve çalıştırma gözlemleriyle puanlar."""

    success = evaluate_criterion(task.criterion, execution)
    return TaskResult(
        task_id=task.id,
        success=success,
        first_attempt_success=success and execution.retries == 0,
        retries=execution.retries,
        model_calls=execution.model_calls,
        duration_seconds=execution.duration_seconds,
    )


def _mean(values: list[float]) -> float:
    """Boş listede 0.0 döner; sıfıra bölme yapılmaz."""

    return sum(values) / len(values) if values else 0.0


@dataclass(frozen=True, slots=True)
class RunReport:
    """Bir değerlendirme çalıştırmasının tüm görev sonuçları ve özet metrikleri."""

    results: tuple[TaskResult, ...]

    @property
    def task_count(self) -> int:
        return len(self.results)

    @property
    def task_success_rate(self) -> float:
        """Başarılı görevlerin oranı (0..1)."""

        return _mean([1.0 if r.success else 0.0 for r in self.results])

    @property
    def first_attempt_success_rate(self) -> float:
        """İlk denemede başarılı görevlerin oranı (0..1)."""

        return _mean([1.0 if r.first_attempt_success else 0.0 for r in self.results])

    @property
    def total_retries(self) -> int:
        return sum(r.retries for r in self.results)

    @property
    def mean_model_calls(self) -> float:
        return _mean([float(r.model_calls) for r in self.results])

    @property
    def mean_duration_seconds(self) -> float:
        return _mean([r.duration_seconds for r in self.results])

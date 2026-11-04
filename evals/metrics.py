"""Görev sonuçları ve çalıştırma raporu — saf toplama.

Ham çalıştırma gözlemlerini (başarı ölçütüyle birlikte) tek görev sonucuna, görev
sonuçlarını da tüm çalıştırmayı özetleyen orana/ortalamaya çevirir. Hiçbir yan
etkisi yoktur; doğrudan test edilir.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from evals.candidate_metrics import CandidateMetrics, reduce_candidate_metrics
from evals.criteria import evaluate_criterion
from evals.execution import TaskExecution
from evals.interactions import InteractionMetrics, merge_interactions
from evals.profiles import RunMetadata
from evals.tasks import EvalTask
from fusion_cli.core.events import Event


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
    #: Sağlayıcı kotası yüzünden ölçülemedi mi?
    rate_limited: bool = False
    rate_limit_detail: str = ""
    #: Görevin kaç kez koşturulduğu (varsayılan 1).
    runs: int = 1
    #: Kaç koşuda geçtiği.
    passes: int = 1
    #: Agent "bitti" dedi ama ölçüt TUTMADI mı?
    #
    # Sıradan başarısızlıktan ayrı sayılır ve kabul eşiği SIFIRDIR: başarısız bir
    # tur kullanıcıyı yalnız oyalar, yalan başarı ise yanlış bilgiyle bırakır —
    # kullanıcı işin bittiğine inanıp üstüne inşa eder. 17 Eylül denetiminin en
    # pahalı bulgu sınıfı buydu ve o güne kadar HİÇ ölçülmüyordu.
    false_success: bool = False
    trace_events: tuple[Event, ...] = ()
    interactions: InteractionMetrics | None = None

    @property
    def pass_rate(self) -> float:
        """Geçme oranı. Tek koşuda 0.0 ya da 1.0'dır; asıl değeri tekrarda ortaya çıkar."""
        return self.passes / self.runs if self.runs else 0.0

    @property
    def kararli(self) -> bool:
        """Görev her koşuda AYNI sonucu verdi mi?

        Kararsız bir görev "geçti"/"kaldı" diye özetlenemez: bir ayarın etkisini
        ölçerken kararsızlık, ölçülen farkın gürültü olabileceği anlamına gelir.
        """
        return self.passes in (0, self.runs)


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
        runs=1,
        passes=1 if success else 0,
        rate_limited=execution.rate_limited,
        rate_limit_detail=execution.rate_limit_detail,
        # Kota yüzünden ölçülemeyen tur yalan başarı DEĞİLDİR: agent orada
        # bitirdiğini iddia etmiyor, sağlayıcı turu kesiyor.
        false_success=execution.claimed_success and not success and not execution.rate_limited,
        trace_events=execution.trace_events,
        interactions=execution.interactions,
    )


def merge_runs(results: list[TaskResult]) -> TaskResult:
    """Aynı görevin N koşusunu tek sonuca indir.

    `success` ÇOĞUNLUKLA değil, HEPSİ geçtiyse doğrudur: bir görev bazen kalıyorsa
    o yetenek güvenilir değildir ve "geçti" demek yanıltıcı olur. Ayrıntı `pass_rate`
    ve `kararli` alanlarındadır.
    """
    ilk = results[0]
    gecen = sum(1 for item in results if item.success)
    return TaskResult(
        task_id=ilk.task_id,
        success=gecen == len(results),
        first_attempt_success=all(item.first_attempt_success for item in results),
        retries=sum(item.retries for item in results),
        model_calls=round(_mean([float(item.model_calls) for item in results])),
        duration_seconds=_mean([item.duration_seconds for item in results]),
        runs=len(results),
        passes=gecen,
        rate_limited=any(item.rate_limited for item in results),
        rate_limit_detail="; ".join(
            item.rate_limit_detail for item in results if item.rate_limited
        ),
        # Tek koşuda bile yalan başarı verdiyse görev yalan başarı sayılır:
        # eşiği sıfır olan bir metrik çoğunluğa yuvarlanamaz.
        false_success=any(item.false_success for item in results),
        trace_events=tuple(event for item in results for event in item.trace_events),
        interactions=merge_interactions(tuple(item.interactions for item in results)),
    )


def _mean(values: list[float]) -> float:
    """Boş listede 0.0 döner; sıfıra bölme yapılmaz."""

    return sum(values) / len(values) if values else 0.0


@dataclass(frozen=True, slots=True)
class RunReport:
    """Bir değerlendirme çalıştırmasının tüm görev sonuçları ve özet metrikleri."""

    results: tuple[TaskResult, ...]
    metadata: RunMetadata | None = None
    candidate_metrics: CandidateMetrics | None = None

    def __post_init__(self) -> None:
        events = tuple(event for result in self.results for event in result.trace_events)
        if self.candidate_metrics is None and events:
            object.__setattr__(self, "candidate_metrics", reduce_candidate_metrics(events))

    @classmethod
    def from_events(
        cls,
        results: tuple[TaskResult, ...],
        events: Sequence[Event],
        *,
        metadata: RunMetadata | None = None,
    ) -> RunReport:
        """Genel tipli trace akışını kayıpsız aday raporuna bağla."""
        return cls(results, metadata, reduce_candidate_metrics(events))

    @property
    def task_count(self) -> int:
        return len(self.results)

    @property
    def task_success_rate(self) -> float:
        """Başarılı görevlerin oranı (0..1)."""

        return _mean([1.0 if r.success else 0.0 for r in self.results])

    @property
    def run_success_rate(self) -> float:
        """Bütün tekrarların tek tek geçme oranı; kararsızlığı görünür tutar."""
        runs = sum(result.runs for result in self.results)
        return sum(result.passes for result in self.results) / runs if runs else 0.0

    @property
    def strict_task_success_rate(self) -> float:
        """Yalnız her tekrarı geçen görevlerin oranı."""
        return self.task_success_rate

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

    @property
    def false_success_tasks(self) -> tuple[str, ...]:
        """Agent'ın bitirdiğini söylediği ama ölçütün tutmadığı görevler."""
        return tuple(result.task_id for result in self.results if result.false_success)

    @property
    def false_success_count(self) -> int:
        return len(self.false_success_tasks)

    @property
    def measured_task_count(self) -> int:
        """Kota yüzünden ölçülemeyenler DIŞINDA kalan görev sayısı."""
        return sum(1 for result in self.results if not result.rate_limited)

    @property
    def completion_rate(self) -> float:
        """Ölçülebilen görevlerin, tamamı içindeki oranı.

        Uzun oturum kabulü ("21/21 tamamlanma") bunu okur: bir tur sağlayıcı
        kotasına takılıp hiç ölçülemediyse oturum tamamlanmamıştır.
        """
        return _mean([1.0 if not r.rate_limited else 0.0 for r in self.results])

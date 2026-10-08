"""İşin başlatılma sırası ve tamamlanma kanıtını tekilleştirir."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ...core.evidence import ToolUse
from ...core.job_evidence import JobCompletion, JobPhase


@dataclass(frozen=True, slots=True)
class JobDelivery:
    completion: JobCompletion
    launch_index: int | None
    launch_evidence: JobCompletion | None = None
    is_superseded: bool = False

    @property
    def problem(self) -> str:
        if self.is_superseded:
            return ""
        job = self.completion
        if job.phase is not JobPhase.COMPLETED:
            return f"İş {job.job_id} sürüyor; tamamlanma kanıtı yok."
        if job.exit_code != 0:
            return f"İş {job.job_id} başarısız: çıkış {job.exit_code}."
        if self.launch_index is None:
            return f"İş {job.job_id} başlangıcı bu turda gözlenmedi; kanıt bağlanamadı."
        launch = self.launch_evidence
        if launch is not None and (
            launch.command != job.command
            or launch.sources_before != job.sources_before
            or tuple((item.path, item.before_hash) for item in launch.outputs)
            != tuple((item.path, item.before_hash) for item in job.outputs)
        ):
            return f"İş {job.job_id} başlangıç ve sonuç kapsamı uyuşmuyor."
        if job.sources_before and job.sources_before != job.sources_after:
            return f"İş {job.job_id} çalışırken kaynak değişti; teslim kanıtı eskidi."
        if any(not receipt.is_refreshed for receipt in job.outputs):
            return f"İş {job.job_id} beklenen çıktı eksik veya yenilendiği kanıtlanmadı."
        return ""


def collect_job_deliveries(tool_uses: tuple[ToolUse, ...]) -> tuple[JobDelivery, ...]:
    """Aynı bitmiş işin polling'i yeni çalıştırma değildir."""
    launches: dict[str, int] = {}
    launch_evidence: dict[str, JobCompletion] = {}
    jobs: dict[str, JobCompletion] = {}
    for index, use in enumerate(tool_uses):
        job = use.job_completion
        if job is None:
            continue
        if job.phase is JobPhase.STARTED:
            launches.setdefault(job.job_id, index)
            launch_evidence.setdefault(job.job_id, job)
        jobs[job.job_id] = job
    deliveries = tuple(
        JobDelivery(job, launches.get(job_id), launch_evidence.get(job_id))
        for job_id, job in jobs.items()
    )
    return tuple(replace(item, is_superseded=_is_resolved(item, deliveries)) for item in deliveries)


def _is_resolved(previous: JobDelivery, deliveries: tuple[JobDelivery, ...]) -> bool:
    """Süren işi kapatma; yalnız aynı kapsamın sonraki taze başarılı retry'ı çözebilir."""
    job = previous.completion
    if job.phase is not JobPhase.COMPLETED or not previous.problem:
        return False
    scope = tuple(item.path for item in job.outputs)
    return any(
        other.completion.job_id != job.job_id
        and not other.problem
        and other.completion.command == job.command
        and tuple(item.path for item in other.completion.outputs) == scope
        and other.launch_index is not None
        and previous.launch_index is not None
        and other.launch_index > previous.launch_index
        for other in deliveries
    )

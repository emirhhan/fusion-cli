"""Yalnız açık iş kapsamının güncel kaynak ve ürün kimliğini ölçer."""

from __future__ import annotations

from pathlib import Path

from ..core.evidence import ToolUse
from ..core.job_evidence import JobCompletion, JobCurrentSnapshot, JobPhase
from ..core.repair_ledger import SourceFingerprint
from .job_delivery import _hash, _safe_path
from .job_evidence import prepare_manifest


def snapshot_current_jobs(root: Path, uses: tuple[ToolUse, ...]) -> tuple[JobCurrentSnapshot, ...]:
    """Polling yerine kapanışta yeni gözlem al; kapsamı komuttan tahmin etme."""
    jobs = {
        use.job_completion.job_id: use.job_completion
        for use in uses
        if use.job_completion is not None
    }
    return tuple(
        _snapshot(root, job)
        for job in jobs.values()
        if job.phase is JobPhase.COMPLETED and job.exit_code == 0
    )


def _snapshot(root: Path, job: JobCompletion) -> JobCurrentSnapshot:
    try:
        sources = _sources(root, job)
        outputs = tuple(
            SourceFingerprint(item.path, _hash(_safe_path(root, item.path)) or "missing")
            for item in job.outputs
        )
        return JobCurrentSnapshot(job.job_id, sources, outputs)
    except (OSError, ValueError):
        return JobCurrentSnapshot(job.job_id, problem="İşin güncel teslim kapsamı doğrulanamadı.")


def _sources(root: Path, job: JobCompletion) -> tuple[SourceFingerprint, ...]:
    if job.source_scopes:
        manifest = prepare_manifest(
            {"failure_check": "final_delivery", "failure_sources": list(job.source_scopes)}, root
        )
        assert manifest is not None
        return manifest.sources
    # Eski receipt yalnız kayıtlı dosyaları ölçer; dizin üyeliği iddiası yoktur.
    return tuple(
        SourceFingerprint(item.path, _hash(_safe_path(root, item.path)) or "missing")
        for item in job.sources_after
    )

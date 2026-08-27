"""Çalıştırma raporunu tek JSON'a yazan/okuyan serileştirme.

Rapor iki bölümden oluşur: her görevin sonucu (`results`) ve özet metrikler
(`summary`). Özet, okumada yeniden hesaplanmaz; ama `to_report` yalnızca
`results`'e güvenerek özeti türetir — tek doğruluk kaynağı görev sonuçlarıdır.
"""

from __future__ import annotations

import json
from pathlib import Path

from evals.metrics import RunReport, TaskResult
from evals.profiles import RunMetadata


def _result_to_dict(result: TaskResult) -> dict[str, object]:
    return {
        "task_id": result.task_id,
        "success": result.success,
        "first_attempt_success": result.first_attempt_success,
        "runs": result.runs,
        "passes": result.passes,
        "pass_rate": result.pass_rate,
        "retries": result.retries,
        "model_calls": result.model_calls,
        "duration_seconds": result.duration_seconds,
    }


def _summary(report: RunReport) -> dict[str, object]:
    return {
        "task_count": report.task_count,
        "task_success_rate": report.task_success_rate,
        "first_attempt_success_rate": report.first_attempt_success_rate,
        "total_retries": report.total_retries,
        "mean_model_calls": report.mean_model_calls,
        "mean_duration_seconds": report.mean_duration_seconds,
    }


def report_to_dict(report: RunReport) -> dict[str, object]:
    """Raporu JSON'a yazılabilir bir sözlüğe çevirir."""

    payload: dict[str, object] = {
        "results": [_result_to_dict(result) for result in report.results],
        "summary": _summary(report),
    }
    if report.metadata is not None:
        payload["metadata"] = {
            "schema_version": report.metadata.schema_version,
            "suite": report.metadata.suite,
            "profile": report.metadata.profile,
            "model": report.metadata.model,
            "repeat": report.metadata.repeat,
            "seed": report.metadata.seed,
            "exclusions": list(report.metadata.exclusions),
        }
    return payload


def report_from_dict(payload: dict[str, object]) -> RunReport:
    """`report_to_dict` çıktısını rapora geri çevirir; özet yeniden türetilir."""

    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        raise ValueError("rapor 'results' bir liste olmalı")
    results = tuple(_result_from_dict(item) for item in raw_results)
    raw_metadata = payload.get("metadata")
    metadata = None
    if isinstance(raw_metadata, dict):
        raw_exclusions = raw_metadata.get("exclusions", [])
        metadata = RunMetadata(
            schema_version=int(raw_metadata.get("schema_version", 2)),
            suite=str(raw_metadata.get("suite", "")),
            profile=str(raw_metadata.get("profile", "fusion-full")),
            model=str(raw_metadata.get("model", "")),
            repeat=int(raw_metadata.get("repeat", 1)),
            seed=None if raw_metadata.get("seed") is None else str(raw_metadata["seed"]),
            exclusions=tuple(str(item) for item in raw_exclusions),
        )
    return RunReport(results=results, metadata=metadata)


def _result_from_dict(item: object) -> TaskResult:
    if not isinstance(item, dict):
        raise ValueError("görev sonucu bir sözlük olmalı")
    return TaskResult(
        task_id=str(item["task_id"]),
        success=bool(item["success"]),
        first_attempt_success=bool(item["first_attempt_success"]),
        runs=int(item.get("runs", 1)),
        passes=int(item.get("passes", 1 if item["success"] else 0)),
        retries=int(item["retries"]),
        model_calls=int(item["model_calls"]),
        duration_seconds=float(item["duration_seconds"]),
    )


def write_report(report: RunReport, path: Path) -> None:
    """Raporu okunabilir (indentli) JSON olarak diske yazar."""

    path.write_text(
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_report(path: Path) -> RunReport:
    """Diskten JSON raporu okur."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("rapor kök öğesi bir sözlük olmalı")
    return report_from_dict(payload)

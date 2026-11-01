"""Çalıştırma raporunu tek JSON'a yazan/okuyan serileştirme.

Rapor iki bölümden oluşur: her görevin sonucu (`results`) ve özet metrikler
(`summary`). Özet, okumada yeniden hesaplanmaz; ama `to_report` yalnızca
`results`'e güvenerek özeti türetir — tek doğruluk kaynağı görev sonuçlarıdır.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from evals.candidate_metrics import CandidateMetrics
from evals.execution import ModelCallIdentity
from evals.metrics import RunReport, TaskResult
from evals.profiles import RunMetadata
from evals.research_contracts import parse_execution_ids, parse_task_budgets


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
        "stable": result.kararli,
        "false_success": result.false_success,
    }


def _summary(report: RunReport) -> dict[str, object]:
    return {
        "task_count": report.task_count,
        "task_success_rate": report.task_success_rate,
        "run_success_rate": report.run_success_rate,
        "strict_task_success_rate": report.strict_task_success_rate,
        "first_attempt_success_rate": report.first_attempt_success_rate,
        "total_retries": report.total_retries,
        "mean_model_calls": report.mean_model_calls,
        "mean_duration_seconds": report.mean_duration_seconds,
        # Eşiği sıfır olan metrik: agent "bitti" dedi, ölçüt tutmadı.
        "false_success_count": report.false_success_count,
        "false_success_tasks": list(report.false_success_tasks),
        "completion_rate": report.completion_rate,
        # Kararsız görev, ölçülen farkın gürültü olabileceğini söyler: bir ayarın
        # etkisini değerlendirirken önce bu listeye bakılır.
        "unstable_tasks": [result.task_id for result in report.results if not result.kararli],
    }


def report_to_dict(report: RunReport) -> dict[str, object]:
    """Raporu JSON'a yazılabilir bir sözlüğe çevirir."""

    payload: dict[str, object] = {
        "results": [_result_to_dict(result) for result in report.results],
        "summary": _summary(report),
    }
    if report.metadata is not None:
        payload["metadata"] = {
            **asdict(report.metadata),
            "exclusions": list(report.metadata.exclusions),
            "unknowns": list(report.metadata.unknowns),
            "calls": [asdict(call) for call in report.metadata.calls],
        }
    if report.candidate_metrics is not None:
        payload["candidate_metrics"] = asdict(report.candidate_metrics)
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
            arm=str(raw_metadata.get("arm", "unknown")),
            requested_model=_optional_text(raw_metadata.get("requested_model")),
            calls=_calls_from_list(raw_metadata.get("calls", [])),
            source_digest=_optional_text(raw_metadata.get("source_digest")),
            prompt_digest=_optional_text(raw_metadata.get("prompt_digest")),
            initial_workspace_digest=_optional_text(raw_metadata.get("initial_workspace_digest")),
            split=_optional_text(raw_metadata.get("split")),
            split_digest=_optional_text(raw_metadata.get("split_digest")),
            scorer_digest=_optional_text(raw_metadata.get("scorer_digest")),
            effective_config_digest=_optional_text(raw_metadata.get("effective_config_digest")),
            environment_digest=_optional_text(raw_metadata.get("environment_digest")),
            corpus_digest=_optional_text(raw_metadata.get("corpus_digest")),
            max_model_calls=_optional_int(raw_metadata.get("max_model_calls")),
            timeout_s=_optional_float(raw_metadata.get("timeout_s")),
            execution_ids=parse_execution_ids(raw_metadata.get("execution_ids")),
            task_config_digests=tuple(
                (str(item[0]), str(item[1])) for item in raw_metadata.get("task_config_digests", [])
            ),
            model_calls_total=_optional_int(raw_metadata.get("model_calls_total")),
            task_ids=tuple(str(item) for item in raw_metadata.get("task_ids", [])),
            task_budgets=parse_task_budgets(raw_metadata.get("task_budgets")),
            corpus_counts=tuple(
                (str(item[0]), int(item[1])) for item in raw_metadata.get("corpus_counts", [])
            ),
            unknowns=tuple(
                str(item)
                for item in raw_metadata.get("unknowns", ["environment", "corpus", "live_baseline"])
            ),
        )
    raw_candidates = payload.get("candidate_metrics")
    candidates = _candidate_metrics(raw_candidates) if raw_candidates is not None else None
    return RunReport(results=results, metadata=metadata, candidate_metrics=candidates)


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
        false_success=bool(item.get("false_success", False)),
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


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Ölçüm sayacı tam sayı veya null olmalı.")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Ölçüm süresi sayı veya null olmalı.")
    return float(value)


def _calls_from_list(value: object) -> tuple[ModelCallIdentity, ...]:
    if not isinstance(value, list):
        raise ValueError("Model çağrıları liste olmalı.")
    calls = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Model çağrısı nesne olmalı.")
        calls.append(
            ModelCallIdentity(
                call_id=str(item["call_id"]),
                role=str(item["role"]),
                requested_model=_optional_text(item.get("requested_model")),
                served_model=_optional_text(item.get("served_model")),
                prompt_tokens=_optional_int(item.get("prompt_tokens")),
                completion_tokens=_optional_int(item.get("completion_tokens")),
                outcome=str(item.get("outcome", "unknown")),
                cost_usd=_optional_float(item.get("cost_usd")),
            )
        )
    return tuple(calls)


def _candidate_metrics(value: object) -> CandidateMetrics:
    """Kaydedilmiş tipli aday özetini doğrula; bilinmeyen oran None kalır."""
    if not isinstance(value, dict):
        raise ValueError("Aday metrikleri nesne olmalı.")
    rates = ("pass_at_1", "oracle_at_2", "selected_at_2", "serial_at_c")
    counts = (
        "candidate_tasks",
        "two_candidate_tasks",
        "lifecycle_calls",
        "abandoned_calls",
        "open_calls",
        "unknown_served_calls",
        "mismatched_model_calls",
        "source_conflicts",
        "rollback_conflicts",
    )
    parsed_rates = [_optional_float(value[name]) for name in rates]
    parsed_counts = [_optional_int(value[name]) for name in counts]
    if any(item is None or item < 0 for item in parsed_counts):
        raise ValueError("Aday sayaçları negatif olamaz ve null olamaz.")
    if any(item is not None and not 0 <= item <= 1 for item in parsed_rates):
        raise ValueError("Aday oranları sıfır ile bir arasında olmalı.")
    return CandidateMetrics(
        pass_at_1=parsed_rates[0],
        oracle_at_2=parsed_rates[1],
        selected_at_2=parsed_rates[2],
        serial_at_c=parsed_rates[3],
        candidate_tasks=_required_count(value["candidate_tasks"]),
        two_candidate_tasks=_required_count(value["two_candidate_tasks"]),
        lifecycle_calls=_required_count(value["lifecycle_calls"]),
        abandoned_calls=_required_count(value["abandoned_calls"]),
        open_calls=_required_count(value["open_calls"]),
        unknown_served_calls=_required_count(value["unknown_served_calls"]),
        mismatched_model_calls=_required_count(value["mismatched_model_calls"]),
        source_conflicts=_required_count(value["source_conflicts"]),
        rollback_conflicts=_required_count(value["rollback_conflicts"]),
        supported_candidate_tasks=_required_count(value.get("supported_candidate_tasks", 0)),
        unsupported_candidate_tasks=_required_count(value.get("unsupported_candidate_tasks", 0)),
        unavailable_candidate_tasks=_required_count(value.get("unavailable_candidate_tasks", 0)),
        unavailable_serial_tasks=_required_count(value.get("unavailable_serial_tasks", 0)),
        step_pass_at_1=_optional_float(value.get("step_pass_at_1")),
        step_oracle_at_2=_optional_float(value.get("step_oracle_at_2")),
        step_selected_at_2=_optional_float(value.get("step_selected_at_2")),
        candidate_steps=_required_count(value.get("candidate_steps", 0)),
        two_candidate_steps=_required_count(value.get("two_candidate_steps", 0)),
    )


def _required_count(value: object) -> int:
    count = _optional_int(value)
    if count is None or count < 0:
        raise ValueError("Aday sayacı pozitif veya sıfır tam sayı olmalı.")
    return count

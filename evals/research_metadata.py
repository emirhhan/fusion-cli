"""Ölçülmüş ortam ve admitted corpus sayısını aynı RunMetadata'ya bağlar."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from evals.execution import TaskExecution
from evals.profiles import RunMetadata
from evals.research_contracts import has_execution_coverage, valid_digest
from fusion_cli.tools.emulation_eval import load_corpus, replay_corpus_report


def complete_metadata(
    metadata: RunMetadata, executions: tuple[TaskExecution, ...], *, corpus: Path | None = None
) -> RunMetadata:
    """Olmayan makbuza değer uydurmaz; kaynak kimliğini ve sayıları birlikte dondur."""
    execution_ids = tuple(
        (item.task_id, item.sample_index) for item in executions if item.sample_index is not None
    )
    covered = has_execution_coverage(
        metadata.task_ids,
        metadata.repeat,
        tuple((item.task_id, item.sample_index) for item in executions),
    ) and all(valid_digest(item.effective_config_digest) for item in executions)
    environment_digest = _environment_digest(executions, covered)
    corpus_digest = None
    counts: tuple[tuple[str, int], ...] = ()
    if corpus is not None:
        cases = load_corpus(corpus)
        report = replay_corpus_report(cases)
        counts = tuple((name, value) for name, value in report.items() if type(value) is int)
        corpus_digest = _digest((hashlib.sha256(corpus.read_bytes()).hexdigest(), counts))
    known = {
        name
        for name, value in (("environment", environment_digest), ("corpus", corpus_digest))
        if value is not None
    }
    configs = tuple(
        (execution.task_id, execution.effective_config_digest)
        for execution in executions
        if execution.effective_config_digest is not None
    )
    unknowns = tuple(name for name in metadata.unknowns if name not in known)
    if environment_digest is None:
        unknowns = tuple(dict.fromkeys((*unknowns, "environment")))
    if not covered:
        unknowns = tuple(dict.fromkeys((*unknowns, "task_effective_config")))
    else:
        unknowns = tuple(name for name in unknowns if name != "task_effective_config")
    return replace(
        metadata,
        execution_ids=execution_ids,
        task_config_digests=configs,
        model_calls_total=sum(execution.model_calls for execution in executions)
        if executions
        else None,
        environment_digest=environment_digest,
        corpus_digest=corpus_digest,
        corpus_counts=counts,
        calls=tuple(call for execution in executions for call in execution.calls),
        unknowns=unknowns,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _environment_digest(executions: tuple[TaskExecution, ...], covered: bool) -> str | None:
    environments: list[tuple[str, str, object]] = []
    missing_environment = not covered
    for execution in executions:
        before = len(environments)
        if execution.runtime_receipt is not None:
            details = json.loads(execution.runtime_receipt.details_json)
            for name in ("environment_before", "environment_after"):
                if details.get(name):
                    environments.append((execution.task_id, name, details[name]))
        for environment in execution.environments:
            environments.append((execution.task_id, "tool", asdict(environment)))
        missing_environment = missing_environment or len(environments) == before
    return _digest(environments) if environments and not missing_environment else None

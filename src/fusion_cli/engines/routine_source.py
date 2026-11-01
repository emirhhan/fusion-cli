"""Rutin önerisi ile çağrısının ortak değişmez plan kaynağı."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..core.execution_plan import ExecutionPlan, VerificationCheckKind
from ..core.memory import RoutineSpec
from ..core.routine_codec import decode_routine, encode_routine
from ..core.task_protocol import args_digest
from ..tools.proposal_policy import is_supported_schema

FILE_KINDS = frozenset({VerificationCheckKind.FILE_EXISTS, VerificationCheckKind.FILE_CONTAINS})


def routine_spec(plan: ExecutionPlan, root: Path) -> RoutineSpec | None:
    """Yalnız açık, desteklenen ve ayrık koşul rollü planı kabul et."""
    definition = plan.routine
    if definition is None or not plan.steps:
        return None
    try:
        raw = encode_routine(definition)
        decode_routine(json.loads(json.dumps(raw)))
        schema = json.loads(definition.input_schema)
    except (ValueError, TypeError):
        return None
    if not is_supported_schema(schema):
        return None
    checks = tuple(check for step in plan.steps for check in step.verification_checks)
    identities = tuple(check.criterion_id for check in checks)
    if len(set(identities)) != len(identities) or set(identities) != {
        *definition.preconditions,
        *definition.checks,
    }:
        return None
    for check in checks:
        target = Path(check.target)
        if check.kind not in FILE_KINDS or not check.target or target.is_absolute():
            return None
        if ".." in target.parts or any(
            (root / Path(*target.parts[:i])).is_symlink() for i in range(1, len(target.parts) + 1)
        ):
            return None
        if check.kind is VerificationCheckKind.FILE_CONTAINS and not check.expected:
            return None
    canonical_schema = json.dumps(schema, sort_keys=True, ensure_ascii=False)
    assert raw is not None
    raw = {
        "input_schema": canonical_schema,
        "preconditions": sorted(definition.preconditions),
        "checks": sorted(definition.checks),
    }
    digest = _source_digest(plan, root, raw)
    return RoutineSpec(
        plan.plan_id,
        plan.task,
        canonical_schema,
        tuple(sorted(definition.preconditions)),
        tuple(sorted(definition.checks)),
        digest,
    )


def _source_digest(plan: ExecutionPlan, root: Path, raw: dict[str, object]) -> str:
    """Yürütme sayaçları dışındaki bütün davranış alanlarını sürüme bağla."""
    steps = []
    for step in plan.steps:
        values = asdict(step)
        for key in ("status", "attempts", "last_progress_fingerprint"):
            values.pop(key)
        steps.append(values)
    return args_digest(
        {
            "plan_id": plan.plan_id,
            "task": plan.task,
            "steps": steps,
            "schema_version": plan.schema_version,
            "routine": raw,
            "root": str(root.resolve()),
        }
    )

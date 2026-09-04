"""Workflow checkpoint'leri için atomik ve toleranslı JSON deposu."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import cast

from ..core.checkpoint import WorkflowCheckpoint
from ..core.execution_plan import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    RetrySafety,
    StepStatus,
)

_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


def _step_to_dict(step: PlanStep) -> dict[str, object]:
    return {
        "step_id": step.step_id,
        "goal": step.goal,
        "depends_on": list(step.depends_on),
        "expected_effects": list(step.expected_effects),
        "allowed_tool_families": list(step.allowed_tool_families),
        "success_criteria": list(step.success_criteria),
        "verification_hint": step.verification_hint,
        "retry_safety": step.retry_safety.value,
        "status": step.status.value,
        "attempts": step.attempts,
    }


def _to_dict(checkpoint: WorkflowCheckpoint) -> dict[str, object]:
    plan = checkpoint.plan
    return {
        "schema_version": 1,
        "plan": {
            "plan_id": plan.plan_id,
            "task": plan.task,
            "schema_version": plan.schema_version,
            "status": plan.status.value,
            "steps": [_step_to_dict(step) for step in plan.steps],
        },
        "root": checkpoint.root,
        "conversation_id": checkpoint.conversation_id,
        "completed_step_ids": list(checkpoint.completed_step_ids),
        "updated_at": checkpoint.updated_at,
    }


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("metin listesi bekleniyordu")
    return tuple(value)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("nesne bekleniyordu")
    return cast("dict[str, object]", value)


def _text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"geçersiz alan: {key}")
    return value


def _integer(data: dict[str, object], key: str, default: int = 0) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"geçersiz alan: {key}")
    return value


def _from_dict(raw: object) -> WorkflowCheckpoint:
    data = _mapping(raw)
    plan_data = _mapping(data.get("plan"))
    steps_raw = plan_data.get("steps")
    if not isinstance(steps_raw, list):
        raise ValueError("geçersiz steps")
    steps: list[PlanStep] = []
    for item in steps_raw:
        step = _mapping(item)
        steps.append(
            PlanStep(
                step_id=_text(step, "step_id"),
                goal=_text(step, "goal"),
                depends_on=_strings(step.get("depends_on")),
                expected_effects=_strings(step.get("expected_effects")),
                allowed_tool_families=_strings(step.get("allowed_tool_families")),
                success_criteria=_strings(step.get("success_criteria")),
                verification_hint=_text(step, "verification_hint"),
                retry_safety=RetrySafety(_text(step, "retry_safety")),
                status=StepStatus(_text(step, "status")),
                attempts=_integer(step, "attempts"),
            )
        )
    updated_at = data.get("updated_at")
    if not isinstance(updated_at, int | float) or isinstance(updated_at, bool):
        raise ValueError("geçersiz updated_at")
    return WorkflowCheckpoint(
        plan=ExecutionPlan(
            plan_id=_text(plan_data, "plan_id"),
            task=_text(plan_data, "task"),
            steps=tuple(steps),
            status=PlanStatus(_text(plan_data, "status")),
            schema_version=_integer(plan_data, "schema_version", 1),
        ),
        root=_text(data, "root"),
        conversation_id=_text(data, "conversation_id"),
        completed_step_ids=_strings(data.get("completed_step_ids")),
        updated_at=float(updated_at),
    )


class JsonCheckpointStore:
    """Her planı ayrı dosyada atomik olarak saklayan yerel depo."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _path(self, plan_id: str) -> Path:
        safe_id = _SAFE_ID.sub("_", plan_id).strip("._") or "plan"
        return self._base_dir / f"{safe_id}.json"

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        target = self._path(checkpoint.plan.plan_id)
        temporary = target.with_suffix(f"{target.suffix}.{os.getpid()}.tmp")
        payload = json.dumps(_to_dict(checkpoint), ensure_ascii=False, indent=2)
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def load(self, plan_id: str) -> WorkflowCheckpoint | None:
        try:
            raw = cast("object", json.loads(self._path(plan_id).read_text(encoding="utf-8")))
            return _from_dict(raw)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def find_resumable(self, root: str, conversation_id: str) -> WorkflowCheckpoint | None:
        matches: list[WorkflowCheckpoint] = []
        try:
            paths = tuple(self._base_dir.glob("*.json"))
        except OSError:
            return None
        for path in paths:
            checkpoint = self.load(path.stem)
            if (
                checkpoint is not None
                and checkpoint.root == root
                and checkpoint.conversation_id == conversation_id
                and checkpoint.plan.status is not PlanStatus.COMPLETED
            ):
                matches.append(checkpoint)
        return max(matches, key=lambda item: item.updated_at, default=None)

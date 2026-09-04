"""Kesintiye dayanıklı workflow checkpoint sözleşmesi."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .execution_plan import ExecutionPlan


@dataclass(frozen=True, slots=True)
class WorkflowCheckpoint:
    """Ham konuşma taşımayan en küçük devam kaydı."""

    plan: ExecutionPlan
    root: str
    conversation_id: str
    completed_step_ids: tuple[str, ...]
    updated_at: float


class CheckpointStore(Protocol):
    """Workflow devam kayıtlarının kalıcılık yüzeyi."""

    def save(self, checkpoint: WorkflowCheckpoint) -> None: ...

    def load(self, plan_id: str) -> WorkflowCheckpoint | None: ...

    def find_resumable(self, root: str, conversation_id: str) -> WorkflowCheckpoint | None: ...

"""Kesintiye dayanıklı workflow checkpoint sözleşmesi."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .evidence import CriterionEvidence, ToolUse
from .execution_plan import ExecutionPlan


@dataclass(frozen=True, slots=True)
class ArtifactFingerprint:
    """Kanıtın ölçüldüğü dosyanın SHA-256 parmak izi."""

    path: str
    digest: str


@dataclass(frozen=True, slots=True)
class StepCheckpointEvidence:
    """Adımın gerçek araç kayıtları, koşul kanıtları ve artifact sürümleri."""

    step_id: str
    criteria: tuple[CriterionEvidence, ...] = ()
    artifacts: tuple[ArtifactFingerprint, ...] = ()
    tool_uses: tuple[ToolUse, ...] = ()
    tool_calls: int = 0
    mutation_calls: int = 0
    already_done_calls: int = 0


@dataclass(frozen=True, slots=True)
class WorkflowBudgetUsage:
    """Bir zarf ve adım kapsamının kaydedilmiş gerçek çağrı harcaması."""

    envelope: str
    scope: str
    calls: int


@dataclass(frozen=True, slots=True)
class WorkflowCheckpoint:
    """Ham konuşma taşımayan en küçük devam kaydı."""

    plan: ExecutionPlan
    root: str
    conversation_id: str
    completed_step_ids: tuple[str, ...]
    updated_at: float
    step_evidence: tuple[StepCheckpointEvidence, ...] = ()
    budget_usage: tuple[WorkflowBudgetUsage, ...] = ()


class CheckpointStore(Protocol):
    """Workflow devam kayıtlarının kalıcılık yüzeyi."""

    def save(self, checkpoint: WorkflowCheckpoint) -> None: ...

    def load(self, plan_id: str) -> WorkflowCheckpoint | None: ...

    def find_resumable(self, root: str, conversation_id: str) -> WorkflowCheckpoint | None: ...

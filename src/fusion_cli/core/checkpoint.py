"""Kesintiye dayanıklı workflow checkpoint sözleşmesi."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .effects import ExternalEffectIntent
from .evidence import CriterionEvidence, ToolUse
from .execution_plan import ExecutionPlan
from .repair_ledger import RepairSnapshot


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
class TurnRepairCheckpoint:
    """Yalnız onarım kanıtı ve mevcut otoritenin tüketilmiş doğrulama hakkı."""

    snapshot: RepairSnapshot
    verify_rounds: int

    def __post_init__(self) -> None:
        if isinstance(self.verify_rounds, bool) or not isinstance(self.verify_rounds, int):
            raise ValueError("Onarım harcaması tam sayı olmalı.")
        if self.verify_rounds < 0:
            raise ValueError("Onarım harcaması negatif olamaz.")


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
    #: Bu oturumda kaç kez bağlam özetlendi.
    #
    # Devam eden tur neyin özetlendiğini bilmelidir: aksi halde "bu dosyayı zaten
    # okumuştum" sanır ya da yapılmış işi yeniden yapar. Sayının kendisi de bir
    # teşhis sinyalidir: çok sık özetleme, bağlamın taşmakta olduğunu söyler.
    condensations: int = 0
    #: Unresolved quality feedback must survive a paused/completed-step resume.
    quality_feedback: str = ""
    turn_repair: TurnRepairCheckpoint | None = None
    storage_revision: int = field(default=0, compare=False)
    effect_intents: tuple[ExternalEffectIntent, ...] = ()
    #: Planın kapsamadığı teslimatlar devamda tamamlanmış sayılmamalı.
    uncovered: tuple[str, ...] = ()


class CheckpointStore(Protocol):
    """Workflow devam kayıtlarının kalıcılık yüzeyi."""

    def save(self, checkpoint: WorkflowCheckpoint) -> int | None: ...

    def load(self, plan_id: str) -> WorkflowCheckpoint | None: ...

    def find_resumable(self, root: str, conversation_id: str) -> WorkflowCheckpoint | None: ...

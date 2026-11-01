"""Gerçek beceri çağrısını mevcut plan, şema ve önkoşul kapısına bağla."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.execution_plan import ExecutionPlan, PlanStatus, StepStatus
from ...core.proposal_invocation import (
    INVOCATION_PREFIX,
    ProposalInvocation,
    ProposalPolicy,
    body_revision,
    proposal_metadata,
    visible_proposal,
)
from ...memory.checkpoint_store import JsonCheckpointStore
from ...memory.skill_proposals import (
    REQUIRED_SUCCESSFUL_RUNS,
    SkillProposalError,
    SkillProposalStore,
)
from ...tools.capabilities import CapabilityRegistry
from ..capability_proposals import PROPOSAL_FILENAME, CapabilityProposals, _parameters

if TYPE_CHECKING:
    from .loop import AgentDeps


class RoutineInvocationValidator:
    """CLI'nin eşzamanlı mevcut hazırlık sınırında da aynı kapıyı kullan."""

    def __init__(self, memory: Path, policy: ProposalPolicy) -> None:
        self.memory = memory
        self.policy = policy

    def __call__(self, proposal: ProposalInvocation, arguments: str, root: Path) -> ExecutionPlan:
        """Öneri kaydı, kaynak sürümü ve güncel önkoşul birlikte geçmeli."""
        if not visible_proposal(proposal, self.policy) or "!`" in arguments:
            raise ValueError("Öneri çağrısı bu split veya parametrelerle desteklenmiyor.")
        store = SkillProposalStore(self.memory / PROPOSAL_FILENAME)
        try:
            saved = next(
                (
                    item
                    for item in store._read()
                    if item.id == proposal.proposal_id
                    and len(item.observations) >= REQUIRED_SUCCESSFUL_RUNS
                ),
                None,
            )
            if (
                saved is None
                or saved.routine != proposal.routine
                or saved.source_split != proposal.source_split
            ):
                raise ValueError("Kurulu önerinin doğrulanmış kaynak kaydı bulunamadı.")
            _parameters(saved, arguments)
            service = CapabilityProposals(
                store,
                JsonCheckpointStore(self.memory / "workflow-checkpoints"),
                root=root,
                installed=root,
                library=CapabilityRegistry(root, root),
            )
            plan = service._validated_plan(saved)
        except SkillProposalError as error:
            raise ValueError(str(error)) from error
        return replace(
            plan,
            status=PlanStatus.PENDING,
            steps=tuple(
                replace(step, status=StepStatus.PENDING, attempts=0, last_progress_fingerprint="")
                for step in plan.steps
            ),
        )


def selected_routine(context: str, deps: AgentDeps) -> tuple[ExecutionPlan, str] | None:
    """Yalnız public invoker'ın tam tipli zarfını aç; prose'dan plan çıkarma."""
    if not context.startswith(INVOCATION_PREFIX):
        return None
    payload = json.loads(context[len(INVOCATION_PREFIX) :].splitlines()[0])
    if not isinstance(payload, dict) or set(payload) != {"path", "arguments", "revision"}:
        raise ValueError("Rutin çağrı zarfı geçersiz.")
    if not all(isinstance(value, str) for value in payload.values()):
        raise ValueError("Rutin çağrı zarfı metin alanları içermeli.")
    path = Path(payload["path"])
    library = deps.capabilities
    if library is None or not any(
        item.path.resolve() == path.resolve() for item in library.skills()
    ):
        raise ValueError("Rutin bu oturumun görünür beceri kataloğunda yok.")
    raw = path.read_text(encoding="utf-8")
    metadata = proposal_metadata(raw)
    if (
        metadata is None
        or metadata.revision != payload["revision"]
        or body_revision(raw) != metadata.revision
    ):
        raise ValueError("Rutin dosyası çağrıdan sonra değişti; yeniden seç.")
    policy = ProposalPolicy(
        deps.config.runtime.verified_skill_proposals, deps.lesson_context.policy.source_split
    )
    plan = RoutineInvocationValidator(deps.config.memory_dir, policy)(
        metadata, payload["arguments"], deps.tool_context.root
    )
    return plan, payload["arguments"]

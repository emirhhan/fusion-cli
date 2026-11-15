"""Tek kök turda ders sunumu ve kanıta bağlı güven güncellemesi."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from ...core.events import LessonOffered, LessonOutcome
from ...core.lesson_runtime import USAGE_UNKNOWN, VERIFIED_OUTCOME, LessonDelivery, LessonUse
from ...core.memory import Lesson, LessonRecallPolicy, RoutineObservation, RoutineSpec
from ...core.verification import VerificationResult

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome
    from .routine_observer import RoutineProof


@dataclass(slots=True)
class LessonTurnState:
    """Kalıcı depo değildir; iç onarımların paylaştığı kök tur muhasebesi."""

    offered: dict[str, Lesson] = field(default_factory=dict)
    uses: dict[str, LessonUse] = field(default_factory=dict)
    verification: VerificationResult | None = None
    routines: list[tuple[RoutineSpec, RoutineObservation]] = field(default_factory=list)
    routine_proofs: dict[str, RoutineProof] = field(default_factory=dict)
    closed: bool = False
    finished: bool = False


def recall_policy(deps: AgentDeps) -> LessonRecallPolicy:
    """Split her bayrak durumunda korunur; çelişki süzgeci açıkça seçilir."""
    return replace(
        deps.lesson_context.policy,
        conflict_quarantine=deps.config.runtime.lesson_conflict_quarantine,
    )


def offer(lessons: tuple[Lesson, ...], deps: AgentDeps, delivery: LessonDelivery) -> None:
    """Metnin gerçekten sunulduğu çağrı noktasından bir kez kaydet."""
    if deps.lesson_state is None:
        deps.lesson_state = LessonTurnState()
    for lesson in lessons:
        if lesson.id and lesson.id not in deps.lesson_state.offered:
            deps.lesson_state.offered[lesson.id] = lesson
            deps.publisher.publish(LessonOffered(lesson.id, delivery))


def settle(outcome: AgentOutcome, deps: AgentDeps) -> None:
    """Kanıtsız retrieval veya prose beyanı hiçbir sonuçta güveni değiştirmez."""
    state = deps.lesson_state
    if state is not None and state.closed:
        return
    lessons = {lesson.id: lesson for lesson in deps.recalled_lessons if lesson.id}
    if state is not None:
        lessons.update(state.offered)
        state.closed = True
    for identity, lesson in lessons.items():
        use = state.uses.get(identity) if state is not None else None
        observation = (
            next(
                (
                    item
                    for routine, item in state.routines
                    if use is not None
                    and routine.routine_id == use.routine_id
                    and routine.source_digest == use.source_digest
                ),
                None,
            )
            if state
            else None
        )
        verified = bool(
            use
            and use.call_ids
            and use.criterion_ids
            and observation
            and observation.verified
            and outcome.ok
            and not outcome.hit_step_limit
            and not outcome.budget_stopped
            and not outcome.model_error
        )
        refs = observation.evidence_refs if verified and observation else ()
        reason = VERIFIED_OUTCOME if verified else USAGE_UNKNOWN
        if deps.lessons is not None:
            deps.lessons.reinforce(
                (lesson.text,),
                success=verified,
                lesson_ids=(identity,),
                used=True if verified else None,
                feedback_reason=reason,
                evidence_refs=refs,
                verified_at=str(deps.clock.now()) if verified else "",
            )
        deps.publisher.publish(
            LessonOutcome(
                identity,
                True if verified else None,
                "success" if verified else "unknown",
                reason,
                refs,
            )
        )
    deps.recalled_lessons.clear()

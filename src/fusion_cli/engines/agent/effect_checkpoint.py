"""Dış etkiyi mevcut plan checkpoint'ine yürütmeden önce bağla."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ...core.effects import EffectPhase, ExternalEffectIntent
from ...core.errors import FusionError
from ...core.execution_plan import RetrySafety
from ...core.tools import AuthorizationScope, Tool, ToolEffect
from ...core.types import ToolCall
from .plan_checkpoint import replace_step

if TYPE_CHECKING:
    from .plan_runner import _PlanRun


class EffectAdmissionError(FusionError):
    """Kalıcı intent veya belirsiz etki varken yeni yazma kabul edilemez."""


def _overlaps(first: AuthorizationScope | None, second: AuthorizationScope | None) -> bool:
    if first is None or second is None:
        return True
    return (
        first.server == second.server
        and first.account == second.account
        and bool(set(first.targets) & set(second.targets))
    )


class PlanEffectRecorder:
    def __init__(self, run: _PlanRun, step_id: str, attempt: int) -> None:
        self.run = run
        self.step_id = step_id
        self.attempt = attempt

    async def prepare(
        self, call: ToolCall, tool: Tool, effect: ToolEffect, scope: AuthorizationScope | None
    ) -> None:
        scope = (
            replace(scope, targets=tuple(sorted(set(scope.targets))))
            if scope is not None and scope.is_complete
            else None
        )
        run = self.run
        if run.deps.checkpoint_store is None or not run.deps.conversation_id:
            raise EffectAdmissionError("Dış işlem için kalıcı devam kaydı yok; işlem başlatılmadı.")
        key = (self.step_id, self.attempt, call.id)
        if key in run.effect_intents or any(
            item.phase is not EffectPhase.RESPONDED and _overlaps(item.scope, scope)
            for item in run.effect_intents.values()
        ):
            raise EffectAdmissionError(
                "Önceki dış işlemin sonucu belirsiz; önce salt-okunur gözlem gerekli."
            )
        step = next(item for item in run.current.steps if item.step_id == self.step_id)
        safety = (
            RetrySafety.NEVER
            if (
                step.retry_safety is RetrySafety.NEVER
                or effect is ToolEffect.REMOTE_DESTRUCTIVE
                or scope is None
                or not scope.is_complete
            )
            else RetrySafety.OBSERVE_FIRST
        )
        run.current = replace_step(run.current, replace(step, retry_safety=safety))
        run.effect_intents[key] = ExternalEffectIntent(
            self.step_id, self.attempt, call.id, tool.name, effect, scope
        )
        await run.save()

    async def finish(self, call_id: str, ok: bool) -> None:
        key = (self.step_id, self.attempt, call_id)
        item = self.run.effect_intents[key]
        self.run.effect_intents[key] = replace(
            item, phase=EffectPhase.RESPONDED if ok else EffectPhase.AMBIGUOUS
        )
        await self.run.save()

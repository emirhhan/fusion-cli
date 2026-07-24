"""Deterministik workflow orkestrasyonu — bütçe kapılı, başarısız-aşama tekrarlı.

Boru hattını sırayla yürütür. Her aşamadan ÖNCE bütçe denetlenir: kalan model
çağrısı yoksa akış durur (`budget_exhausted`). Bir aşama başarısız olursa YALNIZCA
o aşama (en fazla `max_retries` kez) tekrarlanır; başarılı aşamalar tekrarlanmaz.

Aşamaların nasıl çalıştığını bilmez: bir `StageExecutor` protokolüne devreder. Bu
sayede bütçe ve tekrar mantığı sahte yürütücüyle ağsız test edilir.
"""

from __future__ import annotations

from typing import Protocol

from .model import (
    MAX_STAGE_RETRIES,
    PIPELINE,
    Budget,
    Stage,
    StageOutcome,
    WorkflowResult,
)


class StageExecutor(Protocol):
    """Bir aşamayı, önceki aşamaların notlarıyla çalıştıran taraf."""

    async def run(self, stage: Stage, notes: dict[Stage, str]) -> StageOutcome: ...


async def run_workflow(
    executor: StageExecutor,
    *,
    budget: Budget,
    pipeline: tuple[Stage, ...] = PIPELINE,
    max_retries: int = MAX_STAGE_RETRIES,
) -> WorkflowResult:
    """Boru hattını bütçe kapısıyla yürüt. İlk kurtarılamayan aşamada başarısız döner."""

    notes: dict[Stage, str] = {}
    stages_run: list[Stage] = []
    calls_used = 0

    for stage in pipeline:
        attempts = 0
        while True:
            if calls_used >= budget.max_model_calls:
                return WorkflowResult(
                    ok=False,
                    stages_run=tuple(stages_run),
                    model_calls=calls_used,
                    budget_exhausted=True,
                    summary=f"model çağrısı bütçesi doldu ({stage.value} aşamasından önce)",
                )

            outcome = await executor.run(stage, dict(notes))
            calls_used += outcome.model_calls
            attempts += 1
            stages_run.append(stage)

            if outcome.ok:
                if outcome.note:
                    notes[stage] = outcome.note
                break

            if attempts > max_retries:
                return WorkflowResult(
                    ok=False,
                    stages_run=tuple(stages_run),
                    model_calls=calls_used,
                    summary=f"aşama başarısız: {stage.value}",
                )

    return WorkflowResult(
        ok=True,
        stages_run=tuple(stages_run),
        model_calls=calls_used,
        summary="workflow tamamlandı",
        final_note=_last_note(notes, pipeline),
    )


def _last_note(notes: dict[Stage, str], pipeline: tuple[Stage, ...]) -> str:
    """Boru hattındaki son (en geç) aşamaya ait notu döndür; yoksa boş."""
    for stage in reversed(pipeline):
        if notes.get(stage):
            return notes[stage]
    return ""

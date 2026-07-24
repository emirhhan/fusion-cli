"""Faz 5 — deterministik workflow: bütçe kapısı ve başarısız-aşama tekrarı.

Orkestrasyon sahte bir StageExecutor ile ağsız test edilir: her aşamanın sonucunu
ve model-çağrısı maliyetini biz belirleriz.
"""

from __future__ import annotations

from fusion_cli.engines.workflow import Budget, Stage, StageOutcome, run_workflow


class _ScriptedExecutor:
    """Aşama → (ok, model_calls) senaryosuyla çalışan sahte yürütücü.

    `fail_until` verilen aşama için, o aşama kaçıncı denemede başarılı olacağını söyler
    (başarısız-aşama tekrarını sınamak için).
    """

    def __init__(
        self,
        *,
        model_calls: int = 1,
        fail_stage: Stage | None = None,
        fail_forever: bool = False,
        succeed_on_attempt: int = 1,
    ) -> None:
        self._model_calls = model_calls
        self._fail_stage = fail_stage
        self._fail_forever = fail_forever
        self._succeed_on_attempt = succeed_on_attempt
        self.attempts: dict[Stage, int] = {}
        self.order: list[Stage] = []

    async def run(self, stage: Stage, notes: dict[Stage, str]) -> StageOutcome:
        self.order.append(stage)
        self.attempts[stage] = self.attempts.get(stage, 0) + 1
        ok = True
        if stage is self._fail_stage:
            ok = not self._fail_forever and self.attempts[stage] >= self._succeed_on_attempt
        return StageOutcome(ok=ok, model_calls=self._model_calls, note=f"{stage.value}-not")


async def test_basarili_akis_tum_asamalari_gecer():
    executor = _ScriptedExecutor(model_calls=1)
    result = await run_workflow(executor, budget=Budget(max_model_calls=100))
    assert result.ok is True
    assert len(result.stages_run) == 5
    assert result.model_calls == 5
    assert result.final_note == "review-not"


async def test_butce_dolunca_akis_durur():
    executor = _ScriptedExecutor(model_calls=2)
    # Bütçe 3: ilk aşama 2 harcar (kalan 1), ikinci aşama 2 daha harcar (toplam 4),
    # üçüncü aşamadan ÖNCE bütçe dolmuş olur.
    result = await run_workflow(executor, budget=Budget(max_model_calls=3))
    assert result.ok is False
    assert result.budget_exhausted is True
    assert "bütçe" in result.summary


async def test_yalniz_basarisiz_asama_tekrarlanir():
    executor = _ScriptedExecutor(fail_stage=Stage.PATCH, succeed_on_attempt=2)
    result = await run_workflow(executor, budget=Budget(max_model_calls=100), max_retries=1)
    assert result.ok is True
    # PATCH iki kez denendi; diğerleri birer kez.
    assert executor.attempts[Stage.PATCH] == 2
    assert executor.attempts[Stage.LOCALIZE] == 1
    assert executor.attempts[Stage.REVIEW] == 1


async def test_kurtarilamayan_asama_akisi_durdurur():
    executor = _ScriptedExecutor(fail_stage=Stage.VERIFY, fail_forever=True)
    result = await run_workflow(executor, budget=Budget(max_model_calls=100), max_retries=1)
    assert result.ok is False
    assert "verify" in result.summary
    # VERIFY 1 + 1 tekrar = 2 deneme; REVIEW hiç çalışmamalı.
    assert executor.attempts[Stage.VERIFY] == 2
    assert Stage.REVIEW not in executor.attempts


async def test_bos_butce_hicbir_asama_calistirmaz():
    executor = _ScriptedExecutor()
    result = await run_workflow(executor, budget=Budget(max_model_calls=0))
    assert result.ok is False
    assert result.budget_exhausted is True
    assert executor.order == []

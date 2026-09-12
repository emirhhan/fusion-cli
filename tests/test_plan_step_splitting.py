"""Başarısız plan adımının bölünmesi ve bölünemezse kullanıcıya sorulması.

Ölçülmüş çöküş (Godot koşusu, kullanıcı makinesi): `step-1-discovery` düştü,
yeniden plan AYNI hedefi geri getirdi, `merge_replanned_plan` onu haklı olarak
reddetti ve workflow "Yeniden plan aynı başarısız hedefi tekrarladı" diyerek
duraklatıldı. Kullanıcının elinde hiçbir çıktı kalmadı.

Doğru davranış: aynı duvara toslayan adımı PARÇALA; parçalanamıyorsa kararı
kullanıcıya bırak — körlemesine denemeye devam etmek yalnız bütçe yakar.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanPhase,
    PlanStatus,
    PlanStep,
    RetrySafety,
    StepStatus,
)
from fusion_cli.engines.agent import plan_runner
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_generation import PlanGeneration
from fusion_cli.engines.agent.plan_runner import (
    _MAX_STEP_SPLITS,
    _bolme_talimati,
    _PlanRun,
)
from fusion_cli.engines.agent.step_verification import StepVerificationResult
from fusion_cli.engines.workflow.model import BudgetLedger, WorkflowBudget


def _adim(
    step_id: str = "step-1-discovery",
    goal: str = "Çalışma dizinini ve Godot proje dosyalarını keşfet",
    status: StepStatus = StepStatus.FAILED,
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        goal=goal,
        depends_on=(),
        expected_effects=(),
        allowed_tool_families=("files",),
        success_criteria=("dizin içeriği bilinir",),
        verification_hint="listelemeyi denetle",
        retry_safety=RetrySafety.SAFE,
        status=status,
        phase=PlanPhase.DISCOVERY,
    )


def _plan(step: PlanStep) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="deadcells",
        task="Dead Cells tarzı bir oyun yap",
        steps=(step,),
        status=PlanStatus.RUNNING,
    )


def _kosu(step: PlanStep) -> _PlanRun:
    butce = WorkflowBudget(planning=2, per_step=24, recovery=24, final=2)
    return _PlanRun(
        task="Dead Cells tarzı bir oyun yap",
        deps=None,  # type: ignore[arg-type]
        agent=None,  # type: ignore[arg-type]
        current=_plan(step),
        limits=butce,
        ledger=BudgetLedger(butce),
    )


class TestBolmeTalimati:
    def test_adimi_adiyla_anar_ve_parcalamayi_ister(self) -> None:
        talimat = _bolme_talimati(_adim(), 1)

        assert "step-1-discovery" in talimat
        assert "Çalışma dizinini" in talimat
        assert "böl" in talimat.lower()
        assert "deneme 1" in talimat

    def test_ayni_hedefi_tekrar_etmeyi_acikca_yasaklar(self) -> None:
        """Genel 'yeniden planla' isteği aynı hedefi farklı kelimelerle geri
        getiriyordu; talimat ne İSTENMEDİĞİNİ de söylemeli."""
        talimat = _bolme_talimati(_adim(), 2)

        assert "FARKLI" in talimat
        assert "Aynı hedefi yeniden yazma" in talimat


class TestBolmeDongusu:
    @pytest.mark.asyncio
    async def test_ayni_sekil_gelince_bolme_talimatiyla_yeniden_dener(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        istekler: list[str] = []

        async def sahte_plan(task, deps, agent, remaining, _):  # type: ignore[no-untyped-def]
            istekler.append(task)
            return PlanGeneration(plan=_plan(_adim()), calls=1, error="")

        monkeypatch.setattr(plan_runner, "generate_plan", sahte_plan)
        # Birleştirme DAİMA reddeder: model aynı duvara toslamaya devam ediyor.
        monkeypatch.setattr(plan_runner, "merge_replanned_plan", lambda *_: None)

        step = _adim()
        tamam, sebep = await _kosu(step).replan_failed_step(
            step,
            AgentOutcome(final_text="olmadı", messages=[]),
            StepVerificationResult(ok=False, findings=("kanıt yok",), evidence=()),
            "fp-1",
        )

        assert tamam is False
        # İlk istek genel yeniden planlama, sonrakiler BÖLME talimatı taşır.
        assert len(istekler) == _MAX_STEP_SPLITS + 1
        assert "BÖLME TALİMATI" not in istekler[0]
        assert all("BÖLME TALİMATI" in istek for istek in istekler[1:])
        # Karar kullanıcıya devredilir; sessizce pes edilmez.
        assert "daha küçük parçalara da bölünemedi" in sebep
        assert step.goal in sebep

    @pytest.mark.asyncio
    async def test_bolme_tutarsa_daha_fazla_denenmez(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        istekler: list[str] = []
        bolunmus = _plan(
            _adim("step-1a", "Yalnız dizini listele", StepStatus.PENDING)
        )

        async def sahte_plan(task, deps, agent, remaining, _):  # type: ignore[no-untyped-def]
            istekler.append(task)
            return PlanGeneration(plan=bolunmus, calls=1, error="")

        monkeypatch.setattr(plan_runner, "generate_plan", sahte_plan)
        # İlk deneme reddedilir, bölme denemesi kabul edilir.
        sonuclar = iter([None, bolunmus])
        monkeypatch.setattr(plan_runner, "merge_replanned_plan", lambda *_: next(sonuclar))

        step = _adim()
        kosu = _kosu(step)
        monkeypatch.setattr(kosu, "save", lambda: None)
        tamam, sebep = await kosu.replan_failed_step(
            step,
            AgentOutcome(final_text="olmadı", messages=[]),
            StepVerificationResult(ok=False, findings=("kanıt yok",), evidence=()),
            "fp-1",
        )

        assert tamam is True
        assert sebep == ""
        # Bölme tuttuğu anda durulur; kalan denemeler harcanmaz.
        assert len(istekler) == 2

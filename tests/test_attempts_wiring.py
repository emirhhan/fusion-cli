"""Paralel deneme seçimi gerçek adım yürütmesine bağlı.

Denetlendi (6 Eylül): `engines/agent/attempts.py` yazıldı ve test edildi ama plan
yürütücüsü onu HİÇ çağırmıyordu — `ATTEMPTS` zarfı yapılandırılsa bile adım tek
kez koşuyordu. Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.

Özellik OPT-IN kalır: zarf sıfırsa davranış birebir eskisi gibidir.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from fusion_cli.core.execution_plan import ExecutionPlan, VerificationCheck, VerificationCheckKind
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from tests.test_plan_repair import _deps, _step


def _adim(path: str):
    adim = _step("yaz", expected_effects=(f"file:{path}",))
    return replace(
        adim,
        verification_checks=(
            VerificationCheck(
                adim.success_criteria[0], VerificationCheckKind.FILE_CONTAINS, path, "sağlam"
            ),
        ),
    )


def _deneme_butcesi(deps, adet: int):
    runtime = deps.config.runtime
    deps.config = SimpleNamespace(
        runtime=SimpleNamespace(
            workflow_step_calls=runtime.workflow_step_calls,
            workflow_recovery_calls=runtime.workflow_recovery_calls,
            workflow_final_verification_calls=runtime.workflow_final_verification_calls,
            workflow_planning_calls=runtime.workflow_planning_calls,
            workflow_attempt_calls=adet,
        )
    )
    return deps


async def test_zarf_sifirken_adim_tek_kez_kosar(tmp_path):
    deps = _deps(tmp_path)
    turlar: list[str] = []

    async def agent(task, agent_deps, **kwargs):
        turlar.append(task)
        (tmp_path / "kod.py").write_text("sağlam", encoding="utf-8")
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1, tool_calls_made=1)

    await run_execution_plan("iş", deps, agent, plan=ExecutionPlan("a", "iş", (_adim("kod.py"),)))

    assert len(turlar) == 1


async def test_zarf_acikken_adaylar_izole_kopyada_kosar(tmp_path):
    """Ayırt edici kanıt: adaylar ASIL projede değil, izole kopyalarda çalışır.

    Kurtarma turu da adımı ikinci kez koşturur; onu paralel denemeyle karıştırmamak
    için bakılan şey tur SAYISI değil, adayın gördüğü çalışma kökü.
    """
    deps = _deneme_butcesi(_deps(tmp_path), 6)
    kokler: list[str] = []

    async def agent(task, agent_deps, **kwargs):
        kok = agent_deps.tool_context.root
        kokler.append(str(kok))
        # İlk aday yanlış yazar, ikinci aday doğru: seçim kanıta bakmalı.
        icerik = "yanlis" if len(kokler) == 1 else "sağlam"
        (kok / "kod.py").write_text(icerik, encoding="utf-8")
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1, tool_calls_made=1)

    sonuc = await run_execution_plan(
        "iş", deps, agent, plan=ExecutionPlan("b", "iş", (_adim("kod.py"),))
    )

    assert any(kok != str(tmp_path) for kok in kokler), "adaylar izole kopyada koşmalı"
    assert sonuc.ok
    assert (tmp_path / "kod.py").read_text(encoding="utf-8") == "sağlam"

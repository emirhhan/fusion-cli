"""Paralel deneme seçimi gerçek adım yürütmesine bağlı.

Denetlendi (6 Eylül): `engines/agent/attempts.py` yazıldı ve test edildi ama plan
yürütücüsü onu HİÇ çağırmıyordu — `ATTEMPTS` zarfı yapılandırılsa bile adım tek
kez koşuyordu. Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.

Özellik OPT-IN kalır: zarf sıfırsa davranış birebir eskisi gibidir.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    RetrySafety,
    VerificationCheck,
    VerificationCheckKind,
)
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


async def test_aday_zarfi_aday_sayisini_degil_gercek_model_cagrilarini_sayar(tmp_path):
    deps = _deneme_butcesi(_deps(tmp_path), 3)
    verilen_sinirlar: list[int | None] = []

    async def agent(task, agent_deps, **kwargs):
        del task, kwargs
        verilen_sinirlar.append(agent_deps.execution.max_model_calls)
        (agent_deps.tool_context.root / "kod.py").write_text("sağlam", encoding="utf-8")
        # İlk aday bütün ek çağrı zarfını tüketir; ikinci aday başlatılmamalı.
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=3, tool_calls_made=1)

    sonuc = await run_execution_plan(
        "iş", deps, agent, plan=ExecutionPlan("c", "iş", (_adim("kod.py"),))
    )

    assert verilen_sinirlar == [3]
    assert sonuc.model_calls_made == 3


async def test_tum_adaylarin_model_cagrilari_sonuca_yansir(tmp_path):
    deps = _deneme_butcesi(_deps(tmp_path), 6)
    cagrilar = 0

    async def agent(task, agent_deps, **kwargs):
        nonlocal cagrilar
        del task, kwargs
        cagrilar += 1
        icerik = "yanlis" if cagrilar == 1 else "sağlam"
        (agent_deps.tool_context.root / "kod.py").write_text(icerik, encoding="utf-8")
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=2, tool_calls_made=1)

    sonuc = await run_execution_plan(
        "iş", deps, agent, plan=ExecutionPlan("d", "iş", (_adim("kod.py"),))
    )

    assert cagrilar == 2
    assert sonuc.model_calls_made == 4


async def test_adaylar_arac_durumunu_paylasmaz_kazanan_geri_alinabilir(tmp_path):
    deps = _deneme_butcesi(_deps(tmp_path), 6)
    (tmp_path / "kod.py").write_text("ilk\n", encoding="utf-8")
    baglamlar = []

    kapanan_sayfalar = 0

    class Sayfa:
        async def close(self):
            nonlocal kapanan_sayfalar
            kapanan_sayfalar += 1

    async def agent(task, agent_deps, **kwargs):
        del task, kwargs
        baglam = agent_deps.tool_context
        baglamlar.append(baglam)
        yol = baglam.root / "kod.py"
        baglam.changes.record(yol)
        yol.write_text("yanlis\n" if len(baglamlar) == 1 else "sağlam\n", encoding="utf-8")
        baglam.touched.add(yol)
        baglam.browser.page = Sayfa()
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1, tool_calls_made=1)

    await run_execution_plan("iş", deps, agent, plan=ExecutionPlan("e", "iş", (_adim("kod.py"),)))

    assert len(baglamlar) == 2
    assert baglamlar[0].changes is not baglamlar[1].changes
    assert baglamlar[0].touched is not baglamlar[1].touched
    asil_yol = tmp_path / "kod.py"
    assert deps.tool_context.changes.paths == (asil_yol,)
    assert deps.tool_context.touched == {asil_yol}
    assert kapanan_sayfalar == 2
    deps.tool_context.changes.restore()
    assert asil_yol.read_text(encoding="utf-8") == "ilk\n"


async def test_sonraki_basarisiz_adim_onceki_aday_ciktisini_geri_almaz(tmp_path):
    deps = _deneme_butcesi(_deps(tmp_path), 2)
    (tmp_path / "a.py").write_text("eski-a\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("eski-b\n", encoding="utf-8")
    ilk = replace(_adim("a.py"), step_id="a")
    ikinci = replace(
        _adim("b.py"),
        step_id="b",
        depends_on=("a",),
        retry_safety=RetrySafety.NEVER,
    )

    async def agent(task, agent_deps, **kwargs):
        del kwargs
        ad = "a" if "[a]" in task else "b"
        yol = agent_deps.tool_context.root / f"{ad}.py"
        agent_deps.tool_context.changes.record(yol)
        yol.write_text("sağlam\n" if ad == "a" else "yanlış\n", encoding="utf-8")
        agent_deps.tool_context.touched.add(yol)
        return AgentOutcome(
            final_text="tamam",
            messages=[],
            model_calls_made=1,
            tool_calls_made=1,
            ok=ad == "a",
        )

    sonuc = await run_execution_plan(
        "iş", deps, agent, plan=ExecutionPlan("f", "iş", (ilk, ikinci))
    )

    assert not sonuc.ok
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "sağlam\n"
    assert (tmp_path / "b.py").read_text(encoding="utf-8") == "eski-b\n"

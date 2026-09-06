"""Geri alma plan yürütücüsüne bağlı.

Denetlendi (6 Eylül): `core/rollback.py` yazıldı ve test edildi ama plan yürütücüsü
onu HİÇ çağırmıyordu — başarısız deneme diske yarım durum bırakmaya devam ediyordu.
Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.

Ayırt edici senaryo: düşen deneme, başarılı denemenin DOKUNMADIĞI bir artık dosya
bırakır. Geri alma yoksa o dosya diskte kalır ve sonraki adım onunla uğraşır.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.execution_plan import ExecutionPlan, VerificationCheck, VerificationCheckKind
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from tests.test_plan_repair import _deps, _step


def _adim(ad: str, path: str):
    adim = _step(ad, expected_effects=(f"file:{path}",))
    return replace(
        adim,
        verification_checks=(
            VerificationCheck(
                adim.success_criteria[0], VerificationCheckKind.FILE_CONTAINS, path, "sağlam"
            ),
        ),
    )


def _yaz(context, ad: str, icerik: str, tmp_path) -> None:
    """Gerçek araç yolu gibi: yazmadan ÖNCE değişiklik kaydına gir."""
    yol = tmp_path / ad
    context.changes.record(yol)
    yol.write_text(icerik, encoding="utf-8")


async def test_dusen_denemenin_artigi_geri_alinir(tmp_path):
    plan = ExecutionPlan("rb", "iş", (_adim("yaz", "kod.py"),))
    deps = _deps(tmp_path)
    turlar: list[str] = []

    async def agent(task, agent_deps, **kwargs):
        turlar.append(task)
        context = agent_deps.tool_context
        if len(turlar) == 1:
            _yaz(context, "kod.py", "yarim", tmp_path)
            _yaz(context, "artik.py", "yarim kalan deneme", tmp_path)
        else:
            _yaz(context, "kod.py", "sağlam", tmp_path)
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1, tool_calls_made=1)

    sonuc = await run_execution_plan("iş", deps, agent, plan=plan)

    assert sonuc.ok
    assert (tmp_path / "kod.py").read_text(encoding="utf-8") == "sağlam"
    assert not (tmp_path / "artik.py").exists()


async def test_dogrulanan_adim_ciktisi_silinmez(tmp_path):
    plan = ExecutionPlan("rb2", "iş", (_adim("yaz", "kod.py"),))
    deps = _deps(tmp_path)

    async def agent(task, agent_deps, **kwargs):
        _yaz(agent_deps.tool_context, "kod.py", "sağlam", tmp_path)
        _yaz(agent_deps.tool_context, "yan.py", "korunmalı", tmp_path)
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1, tool_calls_made=1)

    sonuc = await run_execution_plan("iş", deps, agent, plan=plan)

    assert sonuc.ok
    assert (tmp_path / "yan.py").is_file()

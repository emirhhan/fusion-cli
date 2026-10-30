"""Adım kapısı önbelleği: mutasyonsuz adımda tekrar build yok, final her zaman tam (A4-16)."""

from __future__ import annotations

from dataclasses import dataclass, field

from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.gate_cache import GateCache, GateScope, step_mutates, workspace_key
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan


class _Publisher:
    def publish(self, event: object) -> None:
        del event


class _SayacliKapi:
    """Çağrı sayısını tutan proje kapısı."""

    def __init__(self, sonuc: VerificationResult | None = None) -> None:
        self.cagri = 0
        self.sonuc = sonuc or VerificationResult(ok=True)

    async def verify(self) -> VerificationResult:
        self.cagri += 1
        return self.sonuc


@dataclass
class _Deps:
    tool_context: ToolContext
    verifier: object | None = None
    execution: object | None = None
    effect_recorder: object | None = None
    budget: object | None = None
    checkpoint_store: object | None = None
    conversation_id: str = ""
    config: object | None = None
    publisher: object = field(default_factory=_Publisher)


def _adim(step_id: str, *, etki: tuple[str, ...] = (), bagimli: tuple[str, ...] = ()) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        goal=f"{step_id} işini yap",
        depends_on=bagimli,
        expected_effects=etki,
        allowed_tool_families=("files",),
        success_criteria=(f"{step_id} kanıtlandı",),
        verification_hint="denetle",
        retry_safety=RetrySafety.SAFE,
    )


async def _koş(tmp_path, adimlar, kapi, yaz):
    deps = _Deps(ToolContext(root=tmp_path), verifier=kapi)

    async def agent(task, turn_deps, **kwargs):
        del kwargs
        ad = next(s.step_id for s in adimlar if f"{s.step_id} işini" in task)
        mutasyon = yaz(ad, tmp_path, turn_deps)
        return AgentOutcome(
            final_text="tamam", messages=[], model_calls_made=1, mutating_tool_calls_made=mutasyon
        )

    plan = ExecutionPlan("p", "iş", tuple(adimlar))
    return await run_execution_plan("iş", deps, agent, plan=plan)


def _yaz_yalniz_ilk(ad, kok, turn_deps):
    if ad != "yaz":
        return 0
    yol = kok / "a.txt"
    yol.write_text("içerik", encoding="utf-8")
    turn_deps.tool_context.touched.add(yol)
    return 1


async def test_salt_okuma_adimlari_gecen_kapiyi_yeniden_kosturmaz(tmp_path):
    """Yazan adım tam kapıyı koşar; ardından gelen iki salt-okuma adımı önbellekten alır."""
    adimlar = [
        _adim("yaz", etki=("file:a.txt",)),
        _adim("oku1", bagimli=("yaz",)),
        _adim("oku2", bagimli=("oku1",)),
    ]
    kapi = _SayacliKapi()

    sonuc = await _koş(tmp_path, adimlar, kapi, _yaz_yalniz_ilk)

    assert sonuc.ok is True
    # taban ölçüm (1) + yazan adım (1) + final kabul (1); iki salt-okuma adımı önbellekten.
    assert kapi.cagri == 3


async def test_mutasyonlu_adim_her_zaman_tam_kapi_kosar(tmp_path):
    adimlar = [
        _adim("a", etki=("workspace_mutation",)),
        _adim("b", etki=("workspace_mutation",), bagimli=("a",)),
    ]
    kapi = _SayacliKapi()

    def yaz(ad, kok, turn_deps):
        yol = kok / f"{ad}.txt"
        yol.write_text(ad, encoding="utf-8")
        turn_deps.tool_context.touched.add(yol)
        return 1

    sonuc = await _koş(tmp_path, adimlar, kapi, yaz)

    assert sonuc.ok is True
    assert kapi.cagri == 4  # taban + iki adım + final


async def test_dokunulan_dosya_degisirse_onbellek_isabet_etmez(tmp_path):
    yol = tmp_path / "a.txt"
    yol.write_text("bir", encoding="utf-8")
    onbellek = GateCache()
    anahtar = workspace_key({yol})
    onbellek.store(anahtar, VerificationResult(ok=True))

    assert onbellek.lookup(anahtar) is not None
    yol.write_text("iki farklı uzunlukta", encoding="utf-8")
    assert onbellek.lookup(workspace_key({yol})) is None


def test_dusen_kapi_onbellege_alinmaz_ve_kaydi_siler():
    onbellek = GateCache()
    onbellek.store("k", VerificationResult(ok=True))
    onbellek.store("k", VerificationResult(ok=False, findings=("kırık",)))

    assert onbellek.lookup("k") is None


def test_kayit_omru_dolunca_isabet_etmez():
    saat = [0.0]
    onbellek = GateCache(ttl_s=10, clock=lambda: saat[0])
    onbellek.store("k", VerificationResult(ok=True))
    saat[0] = 11.0

    assert onbellek.lookup("k") is None


def test_adim_mutasyon_siniflandirmasi():
    assert step_mutates(_adim("a", etki=("file:x.txt",)))
    assert step_mutates(_adim("a", etki=("shell_action",)))
    assert not step_mutates(_adim("a"))
    assert GateScope(GateCache()).outer_touched == frozenset()

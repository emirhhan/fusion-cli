"""Tipli plan yürütücüsünün sıralama ve güvenlik davranışı."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from fusion_cli.core.events import (
    ExecutionCompleted,
    ExecutionPlanCreated,
    ExecutionStepStarted,
    ExecutionStepVerified,
)
from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import Message
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from fusion_cli.engines.agent.promotion import PromotionContext


def _step(
    step_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    expected_effects: tuple[str, ...] = (),
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        goal=f"{step_id} işini yap",
        depends_on=depends_on,
        expected_effects=expected_effects,
        allowed_tool_families=("files",),
        success_criteria=(f"{step_id} kanıtlandı",),
        verification_hint="çıktıyı denetle",
        retry_safety=RetrySafety.SAFE,
    )


@dataclass
class _FakeAgent:
    prompts: list[str]

    async def __call__(self, task, deps, **kwargs):
        del deps, kwargs
        self.prompts.append(task)
        step_id = "inspect" if "inspect işini" in task else "patch"
        return AgentOutcome(
            final_text=f"{step_id} tamamlandı",
            messages=[Message("assistant", f"{step_id} tamamlandı")],
            tool_calls_made=1,
            model_calls_made=1,
        )


class _Publisher:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


class _FakeBudget:
    """Idle saatinin tazelenip tazelenmediğini sayan asgari bütçe."""

    def __init__(self):
        self.progress_calls = 0

    def record_progress(self):
        self.progress_calls += 1


@dataclass
class _FakeDeps:
    tool_context: ToolContext
    execution: object | None = None
    budget: object | None = None
    verifier: object | None = None
    checkpoint_store: object | None = None
    conversation_id: str = ""
    config: object | None = None
    publisher: object = field(default_factory=_Publisher)


async def test_runner_bagimli_adimlari_sirayla_calistirir(tmp_path):
    plan = ExecutionPlan(
        plan_id="p",
        task="özellik ekle",
        steps=(_step("inspect"), _step("patch", depends_on=("inspect",))),
    )
    agent = _FakeAgent([])

    result = await run_execution_plan(
        "özellik ekle", _FakeDeps(ToolContext(root=tmp_path)), agent, plan=plan
    )

    assert result.ok is True
    assert len(agent.prompts) == 2
    assert "inspect tamamlandı" in agent.prompts[1]
    assert "patch tamamlandı" in result.final_text


async def test_runner_basarisiz_adimdan_sonra_bagimli_adimi_calistirmaz(tmp_path):
    plan = ExecutionPlan(
        plan_id="p",
        task="özellik ekle",
        steps=(_step("inspect"), _step("patch", depends_on=("inspect",))),
    )

    async def failing_agent(task, deps, **kwargs):
        del task, deps, kwargs
        return AgentOutcome(final_text="başarısız", messages=[], ok=False)

    result = await run_execution_plan(
        "özellik ekle", _FakeDeps(ToolContext(root=tmp_path)), failing_agent, plan=plan
    )

    assert result.ok is False
    assert "inspect" in result.final_text


async def test_gecersiz_model_plani_yalniz_bir_kez_onarilir(tmp_path):
    replies = iter(("{bozuk", "{hala bozuk"))
    calls: list[str] = []

    async def invalid_agent(task, deps, **kwargs):
        del deps, kwargs
        calls.append(task)
        return AgentOutcome(final_text=next(replies), messages=[])

    result = await run_execution_plan(
        "özellik ekle", _FakeDeps(ToolContext(root=tmp_path)), invalid_agent
    )

    assert result.ok is False
    assert len(calls) == 2
    assert "plan üretilemedi" in result.final_text.lower()


async def test_dogrulama_hatasi_onarim_yonergesiyle_bir_kez_yeniden_denir(tmp_path):
    plan = ExecutionPlan(plan_id="p", task="iş", steps=(_step("inspect"),))
    prompts: list[str] = []

    async def agent(task, deps, **kwargs):
        del deps, kwargs
        prompts.append(task)
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1)

    class _Verifier:
        def __init__(self):
            self.calls = 0

        async def verify(self):
            self.calls += 1
            if self.calls == 1:
                return VerificationResult(ok=False, findings=("pytest kırıldı",))
            return VerificationResult(ok=True)

    deps = _FakeDeps(ToolContext(root=tmp_path), verifier=_Verifier())

    result = await run_execution_plan("iş", deps, agent, plan=plan)

    assert result.ok is True
    assert len(prompts) == 2
    assert "KURTARMA YÖNERGESİ" in prompts[1]
    assert "pytest kırıldı" in prompts[1]


async def test_adim_butcesi_asildiginda_basari_uydurmadan_duraklar(tmp_path):
    plan = ExecutionPlan(plan_id="p", task="iş", steps=(_step("inspect"),))
    config = SimpleNamespace(
        runtime=SimpleNamespace(
            workflow_planning_calls=2,
            workflow_step_calls=0,
            workflow_recovery_calls=1,
            workflow_final_verification_calls=1,
        )
    )
    deps = _FakeDeps(ToolContext(root=tmp_path), config=config)

    async def agent(task, agent_deps, **kwargs):
        del task, agent_deps, kwargs
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1)

    result = await run_execution_plan("iş", deps, agent, plan=plan)

    assert result.ok is False
    assert result.budget_stopped is True
    assert "duraklatıldı" in result.final_text


async def test_plan_olaylari_kullaniciya_sirali_ilerleme_sunar(tmp_path):
    plan = ExecutionPlan(plan_id="p", task="iş", steps=(_step("inspect"),))
    deps = _FakeDeps(ToolContext(root=tmp_path))

    async def agent(task, agent_deps, **kwargs):
        del task, agent_deps, kwargs
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1)

    await run_execution_plan("iş", deps, agent, plan=plan)

    event_types = tuple(type(event) for event in deps.publisher.events)
    assert event_types == (
        ExecutionPlanCreated,
        ExecutionStepStarted,
        ExecutionStepVerified,
        ExecutionCompleted,
    )


async def test_yukseltme_baglami_plan_uretimine_tasinir(tmp_path):
    """Hızlı turun kanıtı plan üreten alt tura ulaşmalı; yoksa iş tekrar edilir."""
    prompts: list[str] = []

    async def plan_agent(task, deps, **kwargs):
        del deps, kwargs
        prompts.append(task)
        return AgentOutcome(final_text="{bozuk", messages=[])

    await run_execution_plan(
        "şuna bir bak",
        _FakeDeps(ToolContext(root=tmp_path)),
        plan_agent,
        promotion=PromotionContext(
            task_summary="şuna bir bak",
            reasons=("teşhis ve onarım gerektiren hata",),
            touched_paths=("src/a.py",),
            tool_evidence=("read_file: başarısız",),
        ),
    )

    assert "YÜKSELTME BAĞLAMI" in prompts[0]
    assert "teşhis ve onarım gerektiren hata" in prompts[0]
    assert "src/a.py" in prompts[0]


async def test_yukseltme_yoksa_plan_istemine_baglam_eklenmez(tmp_path):
    prompts: list[str] = []

    async def plan_agent(task, deps, **kwargs):
        del deps, kwargs
        prompts.append(task)
        return AgentOutcome(final_text="{bozuk", messages=[])

    await run_execution_plan(
        "şuna bir bak", _FakeDeps(ToolContext(root=tmp_path)), plan_agent
    )

    assert "YÜKSELTME BAĞLAMI" not in prompts[0]


async def test_her_adim_kendi_cagri_hakkini_alir(tmp_path):
    """Ölçüldü (Godot koşusu): ilk adım tüm planın adım hakkını yiyordu.

    Dört adımlık gerçek koşuda `setup-project` sekiz çağrının hepsini harcadı ve
    kalan üç adım hiç başlamadan workflow duraklatıldı. Her adım kendi zarfını
    almalı; plan uzadıkça adım başına düşen hak azalmamalı.
    """
    plan = ExecutionPlan(
        plan_id="p",
        task="iş",
        steps=(_step("inspect"), _step("patch", depends_on=("inspect",))),
    )
    config = SimpleNamespace(
        runtime=SimpleNamespace(
            workflow_planning_calls=2,
            workflow_step_calls=2,
            workflow_recovery_calls=1,
            workflow_final_verification_calls=1,
        )
    )
    deps = _FakeDeps(ToolContext(root=tmp_path), config=config)
    calisan: list[str] = []

    async def agent(task, agent_deps, **kwargs):
        del agent_deps, kwargs
        calisan.append("inspect" if "inspect işini" in task else "patch")
        # Her adım kendi zarfının TAMAMINI harcar.
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=2)

    result = await run_execution_plan("iş", deps, agent, plan=plan)

    assert calisan == ["inspect", "patch"]
    assert result.budget_stopped is False


async def test_adim_kok_gorevin_etkisiyle_degil_kendi_etkisiyle_calisir(tmp_path):
    """Ölçüldü (Godot koşusu): kök görev metni "godot ... komutunu ÇALIŞTIR" diyordu.

    Kökten çıkarılan `shell_action` zorunluluğu her alt tura miras kaldı ve yalnız
    dosya oluşturan ilk adım "komut çalıştırılmadı" diye başarısız sayıldı; kurtarma
    bütçesi bu sahte hataya harcanıp plan duraklatıldı. Her adımın beklenen etkisi
    planda zaten tipli olarak duruyor.
    """
    plan = ExecutionPlan(
        plan_id="p",
        task="iş",
        steps=(
            _step("inspect", expected_effects=("workspace_mutation",)),
            _step("patch", depends_on=("inspect",)),
        ),
    )
    kok_politika = ExecutionPolicy(
        is_web=False, required_effect="shell_action", requires_tool_evidence=True
    )
    deps = _FakeDeps(ToolContext(root=tmp_path), execution=kok_politika)
    gorulen: list[object] = []

    async def agent(task, agent_deps, **kwargs):
        del task, kwargs
        gorulen.append(agent_deps.execution.required_effect)
        # Adım post-condition'ı gerçekten sağlanır; yoksa plan ilk adımda tekrar eder
        # ve testin ölçtüğü şey ikinci ADIMA hiç ulaşmaz.
        return AgentOutcome(
            final_text="tamam", messages=[], model_calls_made=1, mutating_tool_calls_made=1
        )

    await run_execution_plan("iş", deps, agent, plan=plan)

    # Birinci adım kendi etkisini, etkisiz ikinci adım hiçbir zorunluluk almaz.
    assert gorulen == ["workspace_mutation", None]
    # Kök politika DEĞİŞTİRİLMEZ; adım kapsamı turun tamamına sızmamalı.
    assert kok_politika.required_effect == "shell_action"


async def test_dogrulama_suresi_model_hareketsizligi_sayilmaz(tmp_path):
    """Ölçüldü (Godot koşusu): tur `inactivity` ile öldü ama model yavaş değildi.

    Model çağrıları 6-13 saniye sürüyordu; idle bütçesini tüketen şey Fusion'ın
    KENDİ doğrulama komutuydu (`godot --headless ...`, 120 sn zaman aşımı). Kendi
    işimizi modelin hareketsizliği saymak, uzun kapısı olan her projede turu
    haksız yere öldürür. Hızlı yol bu dersi zaten uyguluyor (`loop.py`).
    """
    plan = ExecutionPlan(plan_id="p", task="iş", steps=(_step("inspect"),))
    budget = _FakeBudget()
    deps = _FakeDeps(ToolContext(root=tmp_path), budget=budget)

    await run_execution_plan("iş", deps, _FakeAgent([]), plan=plan)

    assert budget.progress_calls > 0


async def test_adim_zarfi_alt_turun_hakkindan_kucuk_olamaz(tmp_path):
    """Ölçüldü (Godot koşusu): adım zarfı 8 iken de 24 iken de duraklattı.

    Zarf MODEL ÇAĞRISI sayar; bir adım tek alt-tur olarak çalışır ve o alt-tur
    kendi politika sınırına kadar (web/karmaşık: 28) çağrı harcayabilir. Zarf
    bundan küçük kalırsa fatura, iş DOĞRU giderken kesilir — 19 başarılı araç
    çağrısı yapan adım hiç tamamlanamadan duraklatıldı. Zarfın işi, bir adımın
    tüm planı yemesini önlemektir; alt-turu ikinci kez sınırlamak değil.
    """
    plan = ExecutionPlan(plan_id="p", task="iş", steps=(_step("inspect"),))
    config = SimpleNamespace(
        runtime=SimpleNamespace(
            workflow_planning_calls=2,
            workflow_step_calls=2,
            workflow_recovery_calls=1,
            workflow_final_verification_calls=1,
        )
    )
    deps = _FakeDeps(
        ToolContext(root=tmp_path),
        config=config,
        execution=ExecutionPolicy(is_web=True, max_model_calls=10),
    )

    async def agent(task, agent_deps, **kwargs):
        del task, agent_deps, kwargs
        return AgentOutcome(
            final_text="tamam", messages=[], model_calls_made=10, mutating_tool_calls_made=1
        )

    result = await run_execution_plan("iş", deps, agent, plan=plan)

    assert result.budget_stopped is False


async def test_kanitlanmayan_davranis_kullaniciya_bildirilir(tmp_path):
    """Uyarı yalnız doğrulama nesnesinde kalırsa hiçbir işe yaramaz.

    Kullanıcı "tamamlandı" cümlesini okuyup işin kanıtlandığını sanar — ölçülen
    hata tam olarak buydu.
    """
    plan = ExecutionPlan(plan_id="p", task="iş", steps=(_step("inspect"),))
    deps = _FakeDeps(ToolContext(root=tmp_path))

    result = await run_execution_plan("iş", deps, _FakeAgent([]), plan=plan)

    assert result.ok is True
    assert "davranış kanıtlanmadı" in result.final_text
    tamamlandi = [
        olay for olay in deps.publisher.events if isinstance(olay, ExecutionCompleted)
    ]
    assert tamamlandi and tamamlandi[0].warnings

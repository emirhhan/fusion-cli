"""Final onarımı, gerçek checkpoint kanıtı ve salt-okunur kurtarma."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStatus,
    RetrySafety,
    StepStatus,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore
from fusion_cli.tools import build_registry
from tests.test_plan_runner import _FakeDeps, _step


def _file_step(name, path, *, depends_on=()):
    step = _step(name, depends_on=depends_on, expected_effects=(f"file:{path}",))
    return replace(
        step,
        verification_checks=(
            VerificationCheck(
                step.success_criteria[0],
                VerificationCheckKind.FILE_CONTAINS,
                path,
                "sağlam",
            ),
        ),
    )


def _deps(root, *, recovery=12, final=2):
    deps = _FakeDeps(
        ToolContext(root=root),
        execution=ExecutionPolicy(is_web=False),
        checkpoint_store=JsonCheckpointStore(root / ".cp"),
        conversation_id="conv",
        config=SimpleNamespace(
            runtime=SimpleNamespace(
                workflow_step_calls=24,
                workflow_recovery_calls=recovery,
                workflow_final_verification_calls=final,
                workflow_planning_calls=2,
            )
        ),
    )
    return deps


@pytest.mark.parametrize("recovery,expected_ok", [(12, True), (0, False)])
async def test_final_bozulan_adimi_onarir_bagimsizi_korur(tmp_path, recovery, expected_ok):
    plan = ExecutionPlan(
        "repair",
        "iş",
        (
            _file_step("create", "a.txt"),
            _file_step("independent", "b.txt"),
            _file_step("finish", "c.txt", depends_on=("create",)),
        ),
    )
    deps = _deps(tmp_path, recovery=recovery)
    called = []

    async def agent(task, agent_deps, **kwargs):
        name = next(step.step_id for step in plan.steps if f"[{step.step_id}]" in task)
        called.append(name)
        path = {"create": "a.txt", "independent": "b.txt", "finish": "c.txt"}[name]
        (tmp_path / path).write_text("sağlam")
        if name == "finish" and called.count("finish") == 1:
            (tmp_path / "a.txt").write_text("bozuk")
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1)

    result = await run_execution_plan("iş", deps, agent, plan=plan)
    saved = deps.checkpoint_store.load("repair")
    assert result.ok is expected_ok
    assert called.count("independent") == 1
    assert saved.plan.status is (PlanStatus.COMPLETED if expected_ok else PlanStatus.PAUSED)
    if expected_ok:
        assert called == ["create", "independent", "finish", "create", "finish"]
        assert result.final_verification_calls == 2
        assert saved.step_evidence and saved.budget_usage
    else:
        assert called == ["create", "independent", "finish"]
        assert saved.plan.steps[1].status is StepStatus.COMPLETED


async def test_observe_first_kurtarmasi_yalniz_okuma_yapar(tmp_path):
    step = replace(_step("observe"), retry_safety=RetrySafety.OBSERVE_FIRST)
    deps = _deps(tmp_path)
    seen = []

    async def agent(task, agent_deps, **kwargs):
        seen.append((agent_deps.execution.allow_mutation, kwargs.get("allowed_tools")))
        return AgentOutcome(final_text="timeout", messages=[], ok=False, model_calls_made=1)

    result = await run_execution_plan(
        "iş", deps, agent, plan=ExecutionPlan("observe", "iş", (step,))
    )
    assert not result.ok
    assert len(seen) == 2
    assert seen[1][0] is False
    assert "write_file" not in seen[1][1]
    assert "read_file" in seen[1][1]


async def test_never_final_hatasi_yan_etkiyi_tekrarlamaz(tmp_path):
    step = replace(_file_step("create", "a.txt"), retry_safety=RetrySafety.NEVER)
    plan = ExecutionPlan("never", "iş", (step, _file_step("finish", "b.txt")))
    deps = _deps(tmp_path)
    called = []

    async def agent(task, agent_deps, **kwargs):
        name = "create" if "[create]" in task else "finish"
        called.append(name)
        (tmp_path / ("a.txt" if name == "create" else "b.txt")).write_text("sağlam")
        if name == "finish":
            (tmp_path / "a.txt").unlink()
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1)

    result = await run_execution_plan("iş", deps, agent, plan=plan)
    assert not result.ok
    assert called == ["create", "finish"]
    assert deps.checkpoint_store.load("never").plan.status is PlanStatus.PAUSED


async def test_final_zarfi_sifirsa_kapi_ve_istenmeyen_onarim_calismaz(tmp_path):
    deps = _deps(tmp_path, final=0)

    async def agent(task, agent_deps, **kwargs):
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1)

    result = await run_execution_plan(
        "iş", deps, agent, plan=ExecutionPlan("zero", "iş", (_step("one"),))
    )
    assert not result.ok
    assert result.budget_stopped
    assert result.final_verification_calls == 0
    assert deps.checkpoint_store.load("zero").plan.status is PlanStatus.PAUSED


async def test_arac_aileleri_runtime_yurutmede_de_kisitlanir(tmp_path):
    from fusion_cli.core.types import ToolCall
    from fusion_cli.engines.agent.loop import _execute

    registry = build_registry()
    result, _ = await _execute(
        ToolCall("call", "write_file", "{}"),
        {"path": "forbidden.txt", "content": "x"},
        SimpleNamespace(tool_context=ToolContext(root=tmp_path)),
        registry,
        execution=ExecutionPolicy(is_web=False, allowed_tool_names=frozenset({"read_file"})),
    )
    assert not result.ok
    assert not (tmp_path / "forbidden.txt").exists()


async def test_mutation_engeli_basari_kaniti_uretmez(tmp_path):
    from fusion_cli.core.types import ToolCall
    from fusion_cli.engines.agent.loop import _execute

    result, _ = await _execute(
        ToolCall("call", "write_file", "{}"),
        {},
        SimpleNamespace(),
        build_registry(),
        execution=ExecutionPolicy(is_web=False, allow_mutation=False),
    )
    assert not result.ok


async def test_checkpoint_artifact_degisince_eski_kanit_kullanilmaz(tmp_path):
    from fusion_cli.core.checkpoint import WorkflowCheckpoint
    from fusion_cli.engines.agent.plan_checkpoint import capture_evidence
    from fusion_cli.engines.agent.step_verification import verify_step

    step = replace(_file_step("create", "a.txt"), status=StepStatus.COMPLETED, attempts=1)
    deps = _deps(tmp_path)
    (tmp_path / "a.txt").write_text("sağlam ilk")
    outcome = AgentOutcome(final_text="rapor", messages=[])
    checked = await verify_step(step, outcome, deps)
    saved_evidence = await capture_evidence(step, outcome, checked, tmp_path)
    checkpoint = WorkflowCheckpoint(
        ExecutionPlan("fingerprint", "iş", (step,), status=PlanStatus.PAUSED),
        str(tmp_path.resolve()),
        "conv",
        ("create",),
        1.0,
        step_evidence=(saved_evidence,),
    )
    deps.checkpoint_store.save(checkpoint)
    assert deps.checkpoint_store.load("fingerprint") == checkpoint
    (tmp_path / "a.txt").write_text("sağlam ama farklı")
    called = []

    async def agent(task, agent_deps, **kwargs):
        called.append(task)
        return AgentOutcome(final_text="yeniden ölçüldü", messages=[], model_calls_made=1)

    result = await run_execution_plan("devam", deps, agent)
    assert result.ok
    assert len(called) == 1


async def test_resume_sahte_mutasyon_kaniti_uretmez(tmp_path):
    from fusion_cli.core.checkpoint import WorkflowCheckpoint

    deps = _deps(tmp_path)
    step = replace(
        _step("mutate", expected_effects=("workspace_mutation",)),
        status=StepStatus.COMPLETED,
        attempts=1,
    )
    deps.checkpoint_store.save(
        WorkflowCheckpoint(
            ExecutionPlan("no-fake", "iş", (step,), status=PlanStatus.PAUSED),
            str(tmp_path.resolve()),
            "conv",
            ("mutate",),
            1.0,
        )
    )
    called = []

    async def agent(task, agent_deps, **kwargs):
        called.append(task)
        return AgentOutcome(final_text="iş yapılmadı", messages=[], model_calls_made=1)

    result = await run_execution_plan("devam", deps, agent)
    assert not result.ok
    assert called
    assert result.mutating_tool_calls_made == 0


async def test_tipli_kontrolsuz_adim_olculen_dosyayi_bagimliya_tasir(tmp_path):
    plan = ExecutionPlan(
        "artifact",
        "iş",
        (
            _step("create", expected_effects=("file:a.txt",)),
            _step("use", depends_on=("create",)),
        ),
    )
    deps = _deps(tmp_path)
    prompts = []

    async def agent(task, agent_deps, **kwargs):
        prompts.append(task)
        (tmp_path / "a.txt").write_text("sağlam")
        return AgentOutcome(final_text="tamam", messages=[], tool_calls_made=1, model_calls_made=1)

    result = await run_execution_plan("iş", deps, agent, plan=plan)

    assert result.ok
    assert "üretilen dosya: a.txt" in prompts[1]
    assert "tamam" not in prompts[1].split("BAŞARI KOŞULLARI")[0].split("BAĞIMLILIK KANITLARI")[1]


async def test_adim_kapsami_disindaki_arac_yapi_kapisini_yonlendiremez(tmp_path):
    """Kapı, adımın ÇAĞIRAMAYACAĞI bir araca yönlendirirse iş imkânsız olur.

    Ölçüldü (canlı Godot koşusu): plan `step-4-main-scene` adımını yalnız
    `files` ailesiyle açtı; `godot__save_scene` bu adımda çağrılamıyordu ama
    yapı kapısı hâlâ "sahneyi elle yazma, o araçları kullan" diyordu. Model üç
    turda aynı duvara çarptı, adım bloklandı ve oyun teslim edilemedi.
    """
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.plan_context import step_deps

    context = ToolContext(root=tmp_path)
    context.available_tools.update({"godot__add_node", "godot__save_scene", "read_file"})
    deps = _deps(tmp_path)
    deps.tool_context = context

    dar = step_deps(deps, _step("sahne"), remaining=4, observe=False)

    assert "godot__save_scene" not in dar.tool_context.available_tools
    # Paylaşılan tur durumu KOPYALANMAZ: değişiklik kaydı aynı nesne kalmalı.
    assert dar.tool_context.changes is context.changes


def _tool_names(deps):
    return deps.execution.allowed_tool_names


async def test_adim_kapsami_gozlemi_engellemez(tmp_path):
    """Kapsam YAN ETKİYİ sınırlar, bakmayı değil.

    Ölçüldü (canlı starter koşusu): plan `traceback-okuyup-duzelt` adımını yalnız
    `shell` ailesiyle açtı; model traceback'i okuyup `read_file` demek istedi ve
    "araç bu adımın izin verilen kapsamında değil" cevabını aldı. Aynı koşuda
    `test-ciktisini-okuyup-duzelt` adımında `read_file`, `replace_range` ve
    `edit_file` birlikte kapalıydı: görev yapılamaz hâle geldi.
    """
    from dataclasses import replace as _replace

    from fusion_cli.engines.agent.plan_context import step_deps

    adim = _replace(_step("kabuk"), allowed_tool_families=("shell",))

    dar = step_deps(_deps(tmp_path), adim, remaining=4, observe=False)

    assert "read_file" in _tool_names(dar)
    assert "list_dir" in _tool_names(dar)


async def test_adimin_kendi_etkisi_kapsam_disinda_birakilmaz(tmp_path):
    """Plan `files` ailesini yazmayı unutsa da dosya etkisi olan adım yazabilmeli."""
    from dataclasses import replace as _replace

    from fusion_cli.engines.agent.plan_context import step_deps

    adim = _replace(
        _step("duzelt", expected_effects=("file:metin.py",)),
        allowed_tool_families=("shell",),
    )

    dar = step_deps(_deps(tmp_path), adim, remaining=4, observe=False)

    assert "write_file" in _tool_names(dar)
    assert "replace_range" in _tool_names(dar)


async def test_kapsam_disi_yan_etki_araci_hala_kapalidir(tmp_path):
    """Gevşetme yalnız gözlem ve adımın KENDİ etkisine aittir."""
    from fusion_cli.engines.agent.plan_context import step_deps

    # Adım `files` ailesiyle açıldı ve kabuk etkisi bildirmedi: kabuk kapalı kalır.
    dar = step_deps(
        _deps(tmp_path), _step("yaz", expected_effects=("file:a.txt",)), remaining=4, observe=False
    )

    assert "write_file" in _tool_names(dar)
    assert "run_shell" not in _tool_names(dar)

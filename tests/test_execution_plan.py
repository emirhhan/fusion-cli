"""Tipli yürütme planının yapısal güvenlik kuralları."""

from __future__ import annotations

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    RetrySafety,
    StepStatus,
    ready_steps,
    validate_plan,
)


def _step(
    step_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    goal: str = "işi yap",
    criteria: tuple[str, ...] = ("sonuç doğrulandı",),
    status: StepStatus = StepStatus.PENDING,
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        goal=goal,
        depends_on=depends_on,
        expected_effects=("workspace_mutation",),
        allowed_tool_families=("files",),
        success_criteria=criteria,
        verification_hint="hedef dosyayı oku",
        retry_safety=RetrySafety.SAFE,
        status=status,
    )


def _plan(*steps: PlanStep) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-1",
        task="özellik ekle",
        steps=steps,
        status=PlanStatus.PENDING,
        schema_version=1,
    )


def test_gecerli_plan_kabul_edilir():
    result = validate_plan(_plan(_step("inspect"), _step("patch", depends_on=("inspect",))))

    assert result.ok is True
    assert result.errors == ()


def test_plan_bos_hedefi_reddeder():
    result = validate_plan(_plan(_step("inspect", goal="  ")))

    assert result.errors == ("Plan adımı 'inspect' boş hedef içeriyor.",)


def test_plan_bos_basari_kosulunu_reddeder():
    result = validate_plan(_plan(_step("inspect", criteria=())))

    assert result.errors == ("Plan adımı 'inspect' doğrulanabilir başarı koşulu içermiyor.",)


def test_plan_yinelenen_kimligi_reddeder():
    result = validate_plan(_plan(_step("inspect"), _step("inspect")))

    assert result.errors == ("Plan adımı kimliği yineleniyor: inspect",)


def test_plan_bilinmeyen_bagimliligi_reddeder():
    result = validate_plan(_plan(_step("patch", depends_on=("missing",))))

    assert result.errors == ("Plan adımı 'patch' bilinmeyen bağımlılık içeriyor: missing",)


def test_plan_dongusel_bagimliligi_reddeder():
    result = validate_plan(_plan(_step("a", depends_on=("b",)), _step("b", depends_on=("a",))))

    assert result.errors == ("Plan bağımlılık döngüsü içeriyor: a → b → a",)


def test_ready_steps_yalniz_tamamlanmis_bagimliliklari_olanlari_dondurur():
    plan = _plan(
        _step("inspect", status=StepStatus.COMPLETED),
        _step("patch", depends_on=("inspect",)),
        _step("verify", depends_on=("patch",)),
    )

    assert tuple(step.step_id for step in ready_steps(plan)) == ("patch",)

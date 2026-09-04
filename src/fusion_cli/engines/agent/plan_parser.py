"""Model plan çıktısını çekirdek yürütme sözleşmesine dönüştürür."""

from __future__ import annotations

import json
from typing import cast

from fusion_cli.core.errors import FusionError
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    RetrySafety,
    StepStatus,
    validate_plan,
)


class PlanParseError(FusionError):
    """Model çıktısı geçerli bir yürütme planına dönüştürülemedi."""


def _strip_code_fence(raw: str) -> str:
    """Varsa tek Markdown kod çitini kaldır."""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _decode_plan_object(raw: str) -> object:
    """Model çıktısındaki plan nesnesini ayıkla ve çöz.

    Metnin TAMAMI JSON olmak zorunda değildir; ilk `{` karakterinden itibaren tek
    bir nesne okunur ve sarmalayan metin yok sayılır.

    Ölçüldü (Gemini web, Godot koşusu): kod bloğunun başlık çubuğundaki dil
    etiketi gövdeye yapışıp çıktı `JSON{...}` hâline geldi. Plan kusursuzdu ama
    ayrıştırılamadı; tek onarım hakkı da AYNI etiketle geri gelip harcandı ve
    görev hiç başlamadan düştü. Sayfa süsünü DOM'da eksiksiz ayıklamak daha önce
    ölçülerek riskli bulundu (kapsayıcı silinince kod gövdesi de gidiyordu), bu
    yüzden dayanıklılık burada kurulur ve tüm sağlayıcılar için geçerlidir.

    Tolerans yalnız SARMALAYICI metne aittir: ayıklanan nesne yine şema, tip ve
    DAG kapılarından geçer; geçersiz bir plan bu yolla geçerli hâle GELMEZ.
    """
    text = _strip_code_fence(raw)
    start = text.find("{")
    if start == -1:
        raise PlanParseError("Plan JSON olarak ayrıştırılamadı: nesne bulunamadı")
    try:
        decoded, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise PlanParseError(f"Plan JSON olarak ayrıştırılamadı: {exc.msg}") from exc
    return cast("object", decoded)


def _require_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PlanParseError(f"'{field}' nesne olmalıdır.")
    if not all(isinstance(key, str) for key in value):
        raise PlanParseError(f"'{field}' yalnızca metin anahtarlar içermelidir.")
    return cast("dict[str, object]", value)


def _require_string(data: dict[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str):
        raise PlanParseError(f"Eksik veya geçersiz plan alanı: {field}")
    return value


def _require_strings(data: dict[str, object], field: str) -> tuple[str, ...]:
    value = data.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PlanParseError(f"Eksik veya geçersiz plan alanı: {field}")
    return tuple(value)


def _parse_step(value: object, index: int) -> PlanStep:
    data = _require_mapping(value, f"steps[{index}]")
    required_fields = (
        "step_id",
        "goal",
        "depends_on",
        "expected_effects",
        "allowed_tool_families",
        "success_criteria",
        "verification_hint",
        "retry_safety",
    )
    missing_fields = tuple(field for field in required_fields if field not in data)
    if missing_fields:
        raise PlanParseError(
            f"Eksik plan alanları (steps[{index}]): {', '.join(missing_fields)}"
        )
    step_id = _require_string(data, "step_id")
    goal = _require_string(data, "goal")
    depends_on = _require_strings(data, "depends_on")
    expected_effects = _require_strings(data, "expected_effects")
    allowed_tool_families = _require_strings(data, "allowed_tool_families")
    success_criteria = _require_strings(data, "success_criteria")
    verification_hint = _require_string(data, "verification_hint")
    retry_value = _require_string(data, "retry_safety")
    try:
        retry_safety = RetrySafety(retry_value)
    except ValueError as exc:
        raise PlanParseError(f"Geçersiz retry_safety değeri: {retry_value}") from exc

    return PlanStep(
        step_id=step_id,
        goal=goal,
        depends_on=depends_on,
        expected_effects=expected_effects,
        allowed_tool_families=allowed_tool_families,
        success_criteria=success_criteria,
        verification_hint=verification_hint,
        retry_safety=retry_safety,
        status=StepStatus.PENDING,
    )


def parse_execution_plan(raw: str) -> ExecutionPlan:
    """JSON plan metnini ayrıştır, türle ve DAG kurallarına göre doğrula."""
    data = _require_mapping(_decode_plan_object(raw), "plan")
    steps_value = data.get("steps")
    if not isinstance(steps_value, list):
        raise PlanParseError("Eksik veya geçersiz plan alanı: steps")

    schema_version = data.get("schema_version", 1)
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise PlanParseError("Eksik veya geçersiz plan alanı: schema_version")

    plan = ExecutionPlan(
        plan_id=_require_string(data, "plan_id"),
        task=_require_string(data, "task"),
        steps=tuple(_parse_step(step, index) for index, step in enumerate(steps_value)),
        status=PlanStatus.PENDING,
        schema_version=schema_version,
    )
    validation = validate_plan(plan)
    if not validation.ok:
        raise PlanParseError(" ".join(validation.errors))
    return plan

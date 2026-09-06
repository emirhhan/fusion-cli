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
    VerificationCheck,
    VerificationCheckKind,
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
    """Dize listesi bekle; tek dize gelirse tek elemanlı liste say.

    Ölçüldü (6 Eylül canlı koşusu): model `success_criteria` alanını liste yerine
    tek string yazdı. Alan doluydu ve anlamı belliydi; ayrıştırıcı reddedince tur
    HİÇ araç çağırmadan bitti ve daha önce geçen görevler düştü.

    Tolerans UYDURMA DEĞİLDİR: boş dize ya da yanlış tip hâlâ reddedilir; yalnız
    "tek değer" ile "tek elemanlı liste" arasındaki biçim farkı onarılır.
    """
    value = data.get(field)
    if isinstance(value, str):
        if not value.strip():
            raise PlanParseError(f"Eksik veya geçersiz plan alanı: {field}")
        return (value,)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PlanParseError(f"Eksik veya geçersiz plan alanı: {field}")
    return tuple(value)


def _parse_retry_safety(data: dict[str, object]) -> RetrySafety:
    """Eksik politika ilk yürütmeyi engellemez; otomatik yinelemeye izin vermez.

    Boş veya tanınmayan etki etiketi salt-okunurluk kanıtı değildir: adımın
    araçları yine değişiklik yapabilir. Bu yüzden güvenliği modelin etki
    metninden çıkarmayız. Açıkça verilmiş geçersiz değerler reddedilir.
    """
    if "retry_safety" not in data:
        return RetrySafety.NEVER
    value = data["retry_safety"]
    if not isinstance(value, str):
        raise PlanParseError("Eksik veya geçersiz plan alanı: retry_safety")
    try:
        return RetrySafety(value)
    except ValueError as exc:
        raise PlanParseError(f"Geçersiz retry_safety değeri: {value}") from exc


def _parse_checks(data: dict[str, object], index: int) -> tuple[VerificationCheck, ...]:
    """İsteğe bağlı tipli kontrolleri ayrıştır; eski planlar boş listeyle yaşar."""
    raw_checks = data.get("verification_checks", [])
    if not isinstance(raw_checks, list):
        raise PlanParseError(
            f"Geçersiz doğrulama kontrolü alanı (steps[{index}]): liste olmalıdır."
        )
    checks: list[VerificationCheck] = []
    for check_index, raw_check in enumerate(raw_checks):
        check_data = _require_mapping(
            raw_check, f"steps[{index}].verification_checks[{check_index}]"
        )
        try:
            kind = VerificationCheckKind(_require_string(check_data, "kind"))
        except ValueError as exc:
            raise PlanParseError(
                f"Geçersiz doğrulama kontrolü türü (steps[{index}]): {check_data.get('kind')}"
            ) from exc
        expected = check_data.get("expected", "")
        if not isinstance(expected, str):
            raise PlanParseError("Doğrulama kontrolü 'expected' metin olmalıdır.")
        checks.append(
            VerificationCheck(
                criterion_id=_require_string(check_data, "criterion_id"),
                kind=kind,
                target=_require_string(check_data, "target"),
                expected=expected,
            )
        )
    return tuple(checks)


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
    )
    missing_fields = tuple(field for field in required_fields if field not in data)
    if missing_fields:
        raise PlanParseError(f"Eksik plan alanları (steps[{index}]): {', '.join(missing_fields)}")
    step_id = _require_string(data, "step_id")
    goal = _require_string(data, "goal")
    depends_on = _require_strings(data, "depends_on")
    expected_effects = _require_strings(data, "expected_effects")
    allowed_tool_families = _require_strings(data, "allowed_tool_families")
    success_criteria = _require_strings(data, "success_criteria")
    verification_hint = _require_string(data, "verification_hint")
    retry_safety = _parse_retry_safety(data)

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
        verification_checks=_parse_checks(data, index),
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

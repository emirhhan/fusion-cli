"""Modelin JSON plan çıktısını tipli sözleşmeye çevirme."""

from __future__ import annotations

import pytest

from fusion_cli.core.execution_plan import RetrySafety
from fusion_cli.engines.agent.plan_parser import PlanParseError, parse_execution_plan

VALID_PLAN = """{
  "plan_id": "plan-1",
  "task": "özellik ekle",
  "steps": [{
    "step_id": "inspect",
    "goal": "mevcut kodu incele",
    "depends_on": [],
    "expected_effects": [],
    "allowed_tool_families": ["files"],
    "success_criteria": ["hedef dosya bulundu"],
    "verification_hint": "dosya yolunu kanıtla",
    "retry_safety": "safe"
  }]
}"""


def test_json_plan_tipli_nesneye_cevrilir():
    plan = parse_execution_plan(VALID_PLAN)

    assert plan.plan_id == "plan-1"
    assert plan.steps[0].retry_safety is RetrySafety.SAFE
    assert plan.steps[0].success_criteria == ("hedef dosya bulundu",)


def test_markdown_kod_citi_icerisindeki_plan_okunur():
    plan = parse_execution_plan(f"```json\n{VALID_PLAN}\n```")

    assert plan.plan_id == "plan-1"


def test_gecersiz_json_acik_hata_verir():
    with pytest.raises(PlanParseError, match="Plan JSON olarak ayrıştırılamadı"):
        parse_execution_plan("{bozuk")


def test_eksik_alan_acik_hata_verir():
    with pytest.raises(PlanParseError, match="success_criteria"):
        parse_execution_plan('{"plan_id":"p","task":"t","steps":[{"step_id":"a"}]}')


def test_yapisal_olarak_gecersiz_plan_reddedilir():
    invalid = VALID_PLAN.replace('"goal": "mevcut kodu incele"', '"goal": ""')

    with pytest.raises(PlanParseError, match="boş hedef"):
        parse_execution_plan(invalid)

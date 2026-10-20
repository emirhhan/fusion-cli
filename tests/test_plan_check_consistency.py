"""Plan, aynı adımda iki farklı dosya yolu iddia edemez.

Ölçüldü (7 Eylül canlı Godot koşusu): adımın beklenen etkisi bir yolu, kontrol
hedefi başka bir yolu gösteriyordu. Adım hangi yolu üretirse üretsin biri düşüyor
ve kurtarma hakkı tükeniyordu. Bu, adımın değil PLANIN hatasıdır; planlayıcı tek
bir yeniden üretimle düzeltebilir, adım ise asla düzeltemez.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    VerificationCheck,
    VerificationCheckKind,
    validate_plan,
)
from fusion_cli.engines.agent.plan_parser import PlanParseError, parse_execution_plan
from tests.test_plan_repair import _step


def _plan(step):
    return ExecutionPlan(plan_id="p", task="iş", steps=(step,))


def _adim(effects, *checks):
    return replace(_step("adim", expected_effects=effects), verification_checks=checks)


def test_kontrol_hedefi_beklenen_dosyadan_farkliysa_plan_reddedilir():
    adim = _adim(
        ("file:game_manager.gd",),
        VerificationCheck(
            _step("adim").success_criteria[0],
            VerificationCheckKind.FILE_EXISTS,
            "scripts/game_manager.gd",
        ),
    )

    sonuc = validate_plan(_plan(adim))

    assert not sonuc.ok
    assert "scripts/game_manager.gd" in " ".join(sonuc.errors)


def test_hedef_beklenen_dosyalardan_biriyse_plan_gecerli():
    hedef = "scripts/game_manager.gd"
    adim = _adim(
        (f"file:{hedef}", "workspace_mutation"),
        VerificationCheck(
            _step("adim").success_criteria[0], VerificationCheckKind.FILE_CONTAINS, hedef, "signal"
        ),
    )

    assert validate_plan(_plan(adim)).ok


def test_dosya_vaadi_olmayan_adimda_kontrol_serbest():
    """Mevcut dosyayı düzenleyen adım `file:` etkisi bildirmek zorunda değil."""
    adim = _adim(
        ("workspace_mutation",),
        VerificationCheck(
            _step("adim").success_criteria[0],
            VerificationCheckKind.FILE_CONTAINS,
            "var/olan.py",
            "x",
        ),
    )

    assert validate_plan(_plan(adim)).ok


def test_celiskili_plan_ayristirmada_da_durur():
    ham = """
    {"plan_id": "p", "task": "iş", "schema_version": 2, "steps": [{
      "step_id": "a", "goal": "yaz", "depends_on": [],
      "expected_effects": ["file:game_manager.gd"],
      "allowed_tool_families": ["files"],
      "success_criteria": ["dosya var"],
      "verification_hint": "bak",
      "verification_checks": [{"criterion_id": "dosya var", "kind": "file_exists",
        "target": "scripts/game_manager.gd", "expected": ""}],
      "retry_safety": "safe"}]}
    """

    with pytest.raises(PlanParseError, match=re.escape("scripts/game_manager.gd")):
        parse_execution_plan(ham)

"""Modelin JSON plan çıktısını tipli sözleşmeye çevirme."""

from __future__ import annotations

import pytest

from fusion_cli.core.execution_plan import RetrySafety, VerificationCheckKind
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
    assert plan.steps[0].verification_checks == ()


def test_tipli_dogrulama_kontrolleri_ayristirilir():
    raw = VALID_PLAN.replace(
        '"verification_hint": "dosya yolunu kanıtla",',
        '"verification_hint": "dosya yolunu kanıtla",\n'
        '    "verification_checks": [{'
        '"criterion_id": "hedef dosya bulundu", '
        '"kind": "file_contains", "target": "main.py", '
        '"expected": "def main"}],',
    )

    plan = parse_execution_plan(raw)

    check = plan.steps[0].verification_checks[0]
    assert check.kind is VerificationCheckKind.FILE_CONTAINS
    assert check.target == "main.py"
    assert check.expected == "def main"


def test_bilinmeyen_dogrulama_kontrolu_reddedilir():
    raw = VALID_PLAN.replace(
        '"verification_hint": "dosya yolunu kanıtla",',
        '"verification_hint": "dosya yolunu kanıtla",\n'
        '    "verification_checks": [{'
        '"criterion_id": "hedef dosya bulundu", '
        '"kind": "uydurma", "target": "main.py"}],',
    )

    with pytest.raises(PlanParseError, match="doğrulama kontrolü"):
        parse_execution_plan(raw)


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


def test_kod_blogu_dil_etiketi_yapisik_gelen_plan_okunur():
    """Ölçüldü (Gemini web): kod bloğu başlığındaki "JSON" etiketi gövdeye yapıştı.

    Plan kusursuzdu; yalnız önüne bir kelime eklenmişti. Harness'ın kusuru yüzünden
    tek onarım hakkı harcandı ve görev hiç başlamadan düştü.
    """
    plan = parse_execution_plan(f"JSON{VALID_PLAN}")

    assert plan.plan_id == "plan-1"


def test_plan_oncesi_ve_sonrasi_serbest_metin_ayiklanir():
    plan = parse_execution_plan(f"İşte plan:\n{VALID_PLAN}\nUmarım uygundur.")

    assert plan.plan_id == "plan-1"


def test_json_nesnesi_hic_yoksa_acik_hata_verir():
    with pytest.raises(PlanParseError, match="Plan JSON olarak ayrıştırılamadı"):
        parse_execution_plan("plan üretemedim")


def test_ayiklama_gecersiz_plani_gecerli_yapmaz():
    """Tolerans yalnız SARMALAYICI metne aittir; şema kapısı zayıflamaz."""
    invalid = VALID_PLAN.replace('"goal": "mevcut kodu incele"', '"goal": ""')

    with pytest.raises(PlanParseError, match="boş hedef"):
        parse_execution_plan(f"JSON{invalid}")


def test_python_sozluk_bicimindeki_plan_guvenle_okunur():
    """Gemini/GLM bazen JSON yerine tek tırnaklı Python sözlüğü döndürüyor."""
    pythonish = VALID_PLAN.replace('"', "'")

    plan = parse_execution_plan(pythonish)

    assert plan.plan_id == "plan-1"


@pytest.mark.parametrize(
    "expected", [{"path": "assets/oyun.zip"}, {"query": "ücretsiz çizim", "options": {"limit": 3}}]
)
def test_arac_kontrolunun_nesne_argumanlari_kayipsiz_korunur(expected):
    import json

    data = json.loads(VALID_PLAN)
    data["steps"][0]["verification_checks"] = [
        {
            "criterion_id": "hedef dosya bulundu",
            "kind": "tool",
            "target": "read_file",
            "expected": expected,
        }
    ]
    plan = parse_execution_plan(json.dumps(data))
    assert json.loads(plan.steps[0].verification_checks[0].expected) == expected


@pytest.mark.parametrize("kind", ["file_contains", "command"])
def test_nesne_normalizasyonu_diger_kontrolleri_gevsetmez(kind):
    import json

    data = json.loads(VALID_PLAN)
    data["steps"][0]["verification_checks"] = [
        {
            "criterion_id": "hedef dosya bulundu",
            "kind": kind,
            "target": "main.py",
            "expected": {"text": "def main"},
        }
    ]
    with pytest.raises(PlanParseError, match="expected"):
        parse_execution_plan(json.dumps(data))


def test_python_literal_icindeki_json_disindaki_deger_onarilabilir_hata_verir():
    import json

    data = json.loads(VALID_PLAN)
    data["steps"][0]["verification_checks"] = [
        {
            "criterion_id": "hedef dosya bulundu",
            "kind": "tool",
            "target": "read_file",
            "expected": {"options": {"a", "b"}},
        }
    ]
    with pytest.raises(PlanParseError, match="geçerli bir JSON nesnesi"):
        parse_execution_plan(repr(data))

"""Plan ayrıştırıcısı, zayıf modelin öngörülebilir sapmalarını onarır.

Ölçüldü (6 Eylül canlı koşusu, %66,7'ye düşen set): model plan JSON'unda
`success_criteria` alanını LİSTE yerine tek STRING yazdı. Alan doluydu, anlamı
belliydi, ama ayrıştırıcı reddetti; tur hiç araç çağırmadan bitti ve `bug-fix-tek-dosya`
gibi daha önce geçen görevler düştü.

Biçim toleransı tek değeri tek elemanlı listeye çevirir; eksik yineleme politikası
ise adımı başlatmaya izin verir ama otomatik yineleme yetkisi üretmez.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.core.execution_plan import RetrySafety
from fusion_cli.engines.agent.plan_parser import PlanParseError, parse_execution_plan


def _plan(**degisiklik: object) -> str:
    adim = {
        "step_id": "duzelt",
        "goal": "hatayı düzelt",
        "depends_on": [],
        "expected_effects": ["workspace_mutation"],
        "allowed_tool_families": ["files"],
        "success_criteria": ["hata düzeltildi"],
        "verification_hint": "pytest",
        "retry_safety": "safe",
    }
    adim.update(degisiklik)
    return json.dumps({"plan_id": "p", "task": "iş", "schema_version": 2, "steps": [adim]})


def test_tek_string_basari_kosulu_kabul_edilir():
    plan = parse_execution_plan(_plan(success_criteria="hata düzeltildi"))

    assert plan.steps[0].success_criteria == ("hata düzeltildi",)


def test_tek_string_arac_ailesi_de_kabul_edilir():
    """Aynı sapma her dize listesinde olabilir; tolerans alan bazlı değil tip bazlıdır.

    Not: `depends_on` için tolerans yine DAG kapısına tabidir — var olmayan bir adıma
    bağlanmak biçim değil ANLAM hatasıdır ve reddedilmeye devam eder.
    """
    plan = parse_execution_plan(_plan(allowed_tool_families="files"))

    assert plan.steps[0].allowed_tool_families == ("files",)


def test_bos_string_kabul_edilmez():
    """Tolerans, EKSİK alanı doldurmak değildir."""
    with pytest.raises(PlanParseError):
        parse_execution_plan(_plan(success_criteria="   "))


def test_yanlis_tipli_alan_hala_reddedilir():
    with pytest.raises(PlanParseError):
        parse_execution_plan(_plan(success_criteria=42))


def test_liste_davranisi_degismez():
    plan = parse_execution_plan(_plan(success_criteria=["bir", "iki"]))

    assert plan.steps[0].success_criteria == ("bir", "iki")


@pytest.mark.parametrize(
    "effects", [[], ["read_only"], ["workspace_mutation"], ["external_publish"]]
)
def test_eksik_retry_safety_yineleme_yetkisi_uretmez(effects):
    """Modelin etki etiketi, adımın gerçekten salt-okunur olduğuna kanıt değildir."""
    adim = json.loads(_plan())["steps"][0]
    adim.pop("retry_safety")
    adim["expected_effects"] = effects
    ham = json.dumps({"plan_id": "p", "task": "iş", "schema_version": 2, "steps": [adim]})
    plan = parse_execution_plan(ham)
    assert plan.steps[0].retry_safety is RetrySafety.NEVER


@pytest.mark.parametrize("value", [None, "", "unknown", 42, []])
def test_gecersiz_retry_safety_eksik_alan_sayilmaz(value):
    with pytest.raises(PlanParseError):
        parse_execution_plan(_plan(expected_effects=[], retry_safety=value))


@pytest.mark.parametrize("value", ["safe", "observe_first", "never"])
def test_acik_retry_safety_korunur(value):
    assert parse_execution_plan(_plan(retry_safety=value)).steps[0].retry_safety.value == value


async def test_eksik_retry_ilk_yurutmeyi_acar_timeout_sonrasi_tekrarlamaz(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.plan_runner import run_execution_plan
    from tests.test_plan_runner import _FakeDeps

    data = json.loads(_plan(expected_effects=[]))
    data["steps"][0].pop("retry_safety")
    plan = parse_execution_plan(json.dumps(data))
    calls = []

    async def timeout_after_effect(task, deps, **kwargs):
        calls.append(task)
        return AgentOutcome(final_text="timeout", messages=[], ok=False, model_calls_made=1)

    result = await run_execution_plan(
        "iş", _FakeDeps(ToolContext(root=tmp_path)), timeout_after_effect, plan=plan
    )
    assert len(calls) == 1
    assert not result.ok

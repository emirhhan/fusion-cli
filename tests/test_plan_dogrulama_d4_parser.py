"""Dalga 4 (plan-dogrulama): plan ayrıştırıcı, php_verify, kurtarma ve ilerleme parmak izi.

Her test, 30 Ekim triyajında kodda ÖLÇÜLEN bir kusuru sabitler.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from fusion_cli.engines.agent.plan_parser import PlanParseError, parse_execution_plan


def _adim(**degisiklik: object) -> dict[str, object]:
    adim: dict[str, object] = {
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
    return adim


def _plan_json(**degisiklik: object) -> str:
    return json.dumps(
        {"plan_id": "p", "task": "iş", "schema_version": 2, "steps": [_adim(**degisiklik)]}
    )


# --- A3-08: "yok" anlamına gelen boş değerler planı düşürmez ------------------- #


@pytest.mark.parametrize("bos", ["", None, "yok", "Yok.", "none"])
def test_bos_bagimlilik_degerleri_bos_liste_sayilir(bos):
    """Ölçüldü (29 Ekim): `"depends_on": ""` PlanParseError verip tek onarım hakkını harcıyordu."""
    plan = parse_execution_plan(_plan_json(depends_on=bos, expected_effects=bos))

    assert plan.steps[0].depends_on == ()
    assert plan.steps[0].expected_effects == ()


def test_bos_basari_kosulu_hala_reddedilir():
    with pytest.raises(PlanParseError):
        parse_execution_plan(_plan_json(success_criteria=""))


# --- A3-09: kurtarma dengeli nesne seçer, sondaki virgülü onarır ---------------- #


def test_oncesindeki_suslu_parantezli_ornek_yanlis_nesneyi_secmez():
    """Ölçüldü (29 Ekim): ilk `{`'ten başlayan çözüm `{görev}` örneğini seçip planı düşürüyordu."""
    ham = f"Şablon: {{görev}} yerine şunu yaz.\n{_plan_json()}"

    assert parse_execution_plan(ham).plan_id == "p"


def test_sondaki_virgul_plani_dusurmez():
    ham = _plan_json().replace('"hata düzeltildi"]', '"hata düzeltildi",]')

    assert parse_execution_plan(ham).steps[0].success_criteria == ("hata düzeltildi",)


def test_literal_eval_ozyineleme_hatasi_ayristirma_hatasina_cevrilir():
    ham = "{'a': " * 5000

    with pytest.raises(PlanParseError):
        parse_execution_plan(ham)


# --- A3-06 / A3-07: php_verify -------------------------------------------------- #


def test_child_tema_ust_temadaki_sablonu_yok_saymaz(tmp_path):
    from fusion_cli.engines.agent.php_verify import missing_theme_references

    ust = tmp_path / "wp-content" / "themes" / "ana"
    cocuk = tmp_path / "wp-content" / "themes" / "cocuk"
    (ust / "template-parts").mkdir(parents=True)
    cocuk.mkdir(parents=True)
    (ust / "style.css").write_text("/* Theme Name: Ana */", encoding="utf-8")
    (ust / "template-parts" / "kart.php").write_text("<?php", encoding="utf-8")
    (cocuk / "style.css").write_text("/*\nTheme Name: Cocuk\nTemplate: ana\n*/", encoding="utf-8")
    sayfa = cocuk / "index.php"
    sayfa.write_text("<?php get_template_part('template-parts/kart'); ?>", encoding="utf-8")

    assert missing_theme_references(sayfa, tmp_path) == []


def test_child_tema_gercekten_olmayan_sablonu_yine_bildirir(tmp_path):
    from fusion_cli.engines.agent.php_verify import missing_theme_references

    ust = tmp_path / "ana"
    cocuk = tmp_path / "cocuk"
    ust.mkdir()
    cocuk.mkdir()
    (ust / "style.css").write_text("/* Theme Name: Ana */", encoding="utf-8")
    (cocuk / "style.css").write_text("/* Theme Name: Cocuk\nTemplate: ana */", encoding="utf-8")
    sayfa = cocuk / "index.php"
    sayfa.write_text("<?php get_template_part('yok/olmayan'); ?>", encoding="utf-8")

    assert len(missing_theme_references(sayfa, tmp_path)) == 1


def test_build_ciktisina_basvuru_olmayan_dosya_sayilmaz(tmp_path):
    """Ölçüldü (29 Ekim): `assets/dist/app.js` build öncesi yok; model elle yazmaya zorlanıyordu."""
    from fusion_cli.engines.agent.php_verify import missing_theme_references

    tema = tmp_path / "tema"
    tema.mkdir()
    (tema / "style.css").write_text("/* Theme Name: T */", encoding="utf-8")
    sayfa = tema / "functions.php"
    sayfa.write_text(
        "<?php wp_enqueue_script('a', get_template_directory_uri() . '/assets/dist/app.js');"
        "wp_enqueue_style('b', get_template_directory_uri() . '/css/site.min.css');"
        "wp_enqueue_script('c', get_template_directory_uri() . '/js/olmayan.js');",
        encoding="utf-8",
    )

    bulgular = missing_theme_references(sayfa, tmp_path)

    assert len(bulgular) == 1
    assert "js/olmayan.js" in bulgular[0]


async def test_lint_zaman_asiminda_sureci_oldurur_ve_bekler(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import php_verify

    olaylar: list[str] = []

    class Sahte:
        returncode = None

        async def communicate(self):
            await asyncio.sleep(10)

        def kill(self):
            olaylar.append("kill")
            raise ProcessLookupError  # süreç zaten bitmiş

        async def wait(self):
            olaylar.append("wait")

    async def olustur(*_a, **_k):
        return Sahte()

    monkeypatch.setattr(php_verify.asyncio, "create_subprocess_exec", olustur)
    monkeypatch.setattr(php_verify, "PHP_LINT_TIMEOUT_S", 0.01)

    sonuc = await php_verify._lint("php", tmp_path / "a.php")

    assert "bitmedi" in sonuc
    assert olaylar == ["kill", "wait"]


# --- A3-12: ilerleme parmak izi değişken ayrıntıdan etkilenmez ------------------ #


def test_parmak_izi_zaman_damgasi_ve_pid_farkini_yok_sayar():
    from fusion_cli.core.execution_plan import PlanStep, RetrySafety
    from fusion_cli.engines.agent.progress import progress_fingerprint
    from fusion_cli.engines.agent.step_verification import StepVerificationResult

    adim = PlanStep(
        step_id="a",
        goal="g",
        depends_on=(),
        expected_effects=(),
        allowed_tool_families=("files",),
        success_criteria=("k",),
        verification_hint="h",
        retry_safety=RetrySafety.SAFE,
    )

    def sonuc(cikti: str):
        kullanim = SimpleNamespace(
            name="run_shell", ok=False, arguments={"command": "make"}, output=cikti
        )
        return SimpleNamespace(tool_uses=(kullanim,))

    dogrulama = StepVerificationResult(ok=False, findings=("x",))
    ilk = progress_fingerprint(
        adim, sonuc("[2026-10-29 10:11:12] pid 4812 hata: bağlanamadı /tmp/tmpab12cd"), dogrulama
    )
    ikinci = progress_fingerprint(
        adim, sonuc("[2026-10-29 10:15:40] pid 977 hata: bağlanamadı /tmp/tmpzz99xx"), dogrulama
    )
    baska = progress_fingerprint(adim, sonuc("hata: başka bir şey"), dogrulama)

    assert ilk == ikinci
    assert ilk != baska


# --- A3-11: hata sınıflandırması alt dizeye takılmaz ---------------------------- #


def test_siniflandirma_sayi_ve_kelime_icindeki_alt_dizelere_takilmaz():
    from fusion_cli.core.failure import FailureCategory
    from fusion_cli.engines.agent.recovery import classify_failure
    from fusion_cli.engines.agent.step_verification import StepVerificationResult

    cikti = SimpleNamespace(
        final_text="Dosya 5030 bayt; iç bağlantı sınıfı eklendi", failed_tool_calls=0, ok=False
    )
    kayit = classify_failure(cikti, StepVerificationResult(ok=True))

    assert kayit.category is FailureCategory.UNKNOWN


def test_siniflandirma_gercek_gecici_hatayi_yine_taniyor():
    from fusion_cli.core.failure import FailureCategory
    from fusion_cli.engines.agent.recovery import classify_failure
    from fusion_cli.engines.agent.step_verification import StepVerificationResult

    cikti = SimpleNamespace(
        final_text="HTTP 503 Service Unavailable, bağlantı kesildi", failed_tool_calls=0, ok=False
    )

    assert (
        classify_failure(cikti, StepVerificationResult(ok=True)).category
        is FailureCategory.TRANSIENT
    )


# --- A3-16: komut kontrolü kabuksuz adıma taşınmaz ------------------------------ #


def test_komut_kontrolu_kabuksuz_yurutme_adimina_tasinmaz():
    """Ölçüldü (29 Ekim): kabuksuz hedefte komut kontrolü ölçülemeyip adımı düşürüyordu."""
    from fusion_cli.core.execution_plan import (
        ExecutionPlan,
        PlanPhase,
        PlanStep,
        RetrySafety,
        VerificationCheck,
        VerificationCheckKind,
    )
    from fusion_cli.engines.agent.plan_phase_repair import repair_discovery_phase

    kontrol = VerificationCheck("surum", VerificationCheckKind.COMMAND, "godot --version")

    def adim(step_id, phase, families, depends_on=(), checks=()):
        return PlanStep(
            step_id=step_id,
            goal=step_id,
            depends_on=depends_on,
            expected_effects=(),
            allowed_tool_families=families,
            success_criteria=("surum",),
            verification_hint="",
            retry_safety=RetrySafety.SAFE,
            phase=phase,
            verification_checks=checks,
        )

    kesif = adim("kesif", PlanPhase.DISCOVERY, ("files",), checks=(kontrol,))
    yazim = adim("yaz", PlanPhase.EXECUTION, ("files",), depends_on=("kesif",))
    kabuklu = adim("kur", PlanPhase.EXECUTION, ("files", "shell"), depends_on=("kesif",))

    assert repair_discovery_phase(ExecutionPlan("p", "t", (kesif, yazim)), kesif) is None
    onarilmis = repair_discovery_phase(ExecutionPlan("p", "t", (kesif, yazim, kabuklu)), kesif)
    assert onarilmis is not None
    assert onarilmis.steps[2].verification_checks == (kontrol,)
    assert onarilmis.steps[1].verification_checks == ()


# --- A3-17: klasör hedefi her devamda "değişti" sayılmaz ------------------------ #


def test_klasor_hedefi_ozeti_kararli_ve_degisince_farkli(tmp_path):
    from fusion_cli.engines.agent.plan_checkpoint import _digest

    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.png").write_bytes(b"x")

    ilk = _digest(tmp_path, "assets")
    assert ilk
    assert _digest(tmp_path, "assets") == ilk
    (tmp_path / "assets" / "b.png").write_bytes(b"yy")
    assert _digest(tmp_path, "assets") != ilk
    assert _digest(tmp_path, "yok") == ""


# --- A3-42: çöken temel ölçüm planı başlamadan düşürmez ------------------------- #


async def test_temel_olcum_cokerse_plan_yine_yurur(tmp_path):
    from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.plan_runner import run_execution_plan
    from tests.test_plan_runner import _FakeDeps

    adim = PlanStep(
        step_id="a",
        goal="a işini yap",
        depends_on=(),
        expected_effects=(),
        allowed_tool_families=("files",),
        success_criteria=("a kanıtlandı",),
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
    )

    class Dogrulayici:
        def __init__(self):
            self.calls = 0

        async def verify(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("kapı betiği çöktü")
            return VerificationResult(ok=True)

    async def ajan(task, deps, **kwargs):
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1)

    deps = _FakeDeps(ToolContext(root=tmp_path), verifier=Dogrulayici())
    sonuc = await run_execution_plan("iş", deps, ajan, plan=ExecutionPlan("p", "iş", (adim,)))

    assert sonuc.ok is True

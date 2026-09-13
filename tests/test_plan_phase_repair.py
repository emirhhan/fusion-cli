"""Keşif evresine bağlanmış kabuk kontrolü modele sorulmadan düzeltilir.

Ölçüldü (13 Eylül, Godot koşusu): yürütücü çelişkiyi yakaladı, modelden yeniden
plan istedi, model keşif adımını ikiye böldü ve aynı komut kontrolünü (`godot
--version`) yeni adıma AYNEN taşıdı. İkinci ziyarette onarım hakkı kalmadığı için
on dakikalık koşu hiçbir şey teslim etmeden duraklatıldı.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanPhase,
    PlanStep,
    RetrySafety,
    StepStatus,
    VerificationCheck,
    VerificationCheckKind,
    validate_plan,
)
from fusion_cli.engines.agent.plan_phase_repair import (
    conflicting_checks,
    repair_discovery_phase,
)

KOMUT_KONTROLU = VerificationCheck(
    "godot sürümü doğrulandı", VerificationCheckKind.COMMAND, "godot --version"
)


def _adim(
    step_id: str,
    *,
    phase: PlanPhase = PlanPhase.DISCOVERY,
    families: tuple[str, ...] = ("files",),
    depends_on: tuple[str, ...] = (),
    checks: tuple[VerificationCheck, ...] = (),
    criteria: tuple[str, ...] = ("godot sürümü doğrulandı",),
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        goal=f"{step_id} hedefi",
        depends_on=depends_on,
        expected_effects=(),
        allowed_tool_families=families,
        success_criteria=criteria,
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
        phase=phase,
        verification_checks=checks,
    )


def test_kabuk_isteyen_kesif_adimi_yurutmeye_hizalanir():
    """Adım `shell` ailesini KENDİSİ istemiş; yanlış olan tek şey evre etiketi."""
    adim = _adim("check-godot", families=("shell",), checks=(KOMUT_KONTROLU,))
    plan = ExecutionPlan("p", "oyun yap", (adim,))

    onarilmis = repair_discovery_phase(plan, adim)

    assert onarilmis is not None
    assert onarilmis.steps[0].phase is PlanPhase.EXECUTION
    # Kontrol DÜŞÜRÜLMEZ: ölçüm korunur.
    assert onarilmis.steps[0].verification_checks == (KOMUT_KONTROLU,)
    assert validate_plan(onarilmis).ok


def test_kontrol_bagli_yurutme_adimina_tasinir():
    """Keşif adımı kabuk istemiyorsa kontrol, ona bağlı yürütme adımına gider."""
    kesif = _adim("discover", checks=(KOMUT_KONTROLU,))
    yurutme = _adim(
        "build",
        phase=PlanPhase.EXECUTION,
        families=("files", "shell"),
        depends_on=("discover",),
        criteria=("proje kuruldu",),
    )
    plan = ExecutionPlan("p", "oyun yap", (kesif, yurutme))

    onarilmis = repair_discovery_phase(plan, kesif)

    assert onarilmis is not None
    assert onarilmis.steps[0].verification_checks == ()
    assert onarilmis.steps[1].verification_checks == (KOMUT_KONTROLU,)
    # Taşınan kontrolün koşulu hedef adımda TANIMLI olmalı, yoksa plan geçersiz olur.
    assert KOMUT_KONTROLU.criterion_id in onarilmis.steps[1].success_criteria
    assert validate_plan(onarilmis).ok
    # Keşif adımının koşulu silinmez: koşul hâlâ doğrudur, yalnız orada ölçülmez.
    assert onarilmis.steps[0].success_criteria == kesif.success_criteria


def test_mekanik_cozum_yoksa_karar_yeniden_planlamaya_kalir():
    """Kontrol sessizce düşürülmez: ölçülemeyen koşulla yürümek işi yapılmış saymaktır."""
    adim = _adim("discover", checks=(KOMUT_KONTROLU,))
    plan = ExecutionPlan("p", "oyun yap", (adim,))

    assert repair_discovery_phase(plan, adim) is None


def test_bagli_olmayan_yurutme_adimina_tasinmaz():
    """Bağımlılığı olmayan bir adım, keşfin kanıtını üstlenemez."""
    kesif = _adim("discover", checks=(KOMUT_KONTROLU,))
    ilgisiz = _adim("other", phase=PlanPhase.EXECUTION, families=("shell",), criteria=("x",))
    plan = ExecutionPlan("p", "oyun yap", (kesif, ilgisiz))

    assert repair_discovery_phase(plan, kesif) is None


def test_onarilan_adim_hic_denenmemis_sayilir():
    """Deneme sayacı taşınırsa adım kurtarma kipinde (gözlem turu) başlar."""
    adim = replace(
        _adim("check-godot", families=("shell",), checks=(KOMUT_KONTROLU,)),
        attempts=2,
        status=StepStatus.BLOCKED,
        last_progress_fingerprint="eski",
    )
    plan = ExecutionPlan("p", "oyun yap", (adim,))

    onarilmis = repair_discovery_phase(plan, adim)

    assert onarilmis is not None
    yeni = onarilmis.steps[0]
    assert yeni.attempts == 0
    assert yeni.status is StepStatus.PENDING
    assert yeni.last_progress_fingerprint == ""


def test_yurutme_adiminda_celiski_yok():
    adim = _adim("build", phase=PlanPhase.EXECUTION, families=("shell",), checks=(KOMUT_KONTROLU,))

    assert conflicting_checks(adim) == ()
    assert repair_discovery_phase(ExecutionPlan("p", "iş", (adim,)), adim) is None


def test_kapali_araci_hedefleyen_arac_kontrolu_de_celiskilidir():
    """`kind: tool` kontrolü keşifte kapalı bir aracı hedefliyorsa da çalışamaz."""
    kontrol = VerificationCheck(
        "godot sürümü doğrulandı",
        VerificationCheckKind.TOOL,
        "run_shell",
        '{"command":"godot --version"}',
    )
    adim = _adim("check-godot", families=("shell",), checks=(kontrol,))

    assert conflicting_checks(adim, frozenset({"run_shell"})) == (kontrol,)
    assert conflicting_checks(adim) == ()

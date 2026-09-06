"""Tanı kanıta ve kurtarma yönergesine ulaşır.

Tanı üretmek tek başına işe yaramaz: kurtarma turu "hata metnini oku" yerine
"şu dosyanın şu satırındaki şu belirtiyi düzelt" görevini almalı.
"""

from __future__ import annotations

from fusion_cli.core.execution_plan import PlanStep, RetrySafety
from fusion_cli.engines.agent.recovery import choose_recovery, classify_failure
from fusion_cli.engines.agent.step_verification import StepVerificationResult


class _Outcome:
    final_text = "test düştü"
    failed_tool_calls = 0
    ok = True


def _step() -> PlanStep:
    return PlanStep(
        step_id="duzelt",
        goal="hatayı düzelt",
        depends_on=(),
        expected_effects=("file:player.gd",),
        allowed_tool_families=("files",),
        success_criteria=("oyun açılıyor",),
        verification_hint="godot --headless",
        retry_safety=RetrySafety.SAFE,
    )


def test_kurtarma_yonergesi_taniyi_tasir():
    bulgu = (
        "komut sıfır döndü ama hata bildirdi (script error): godot --headless\n"
        'SCRIPT ERROR: Parse Error: Identifier "velocity" not declared in the current scope.\n'
        "          at: GDScript::reload (res://player.gd:12)"
    )
    dogrulama = StepVerificationResult(ok=False, evidence=(), findings=(bulgu,))

    karar = choose_recovery(classify_failure(_Outcome(), dogrulama), _step(), attempts=1)

    # Yapılandırılmış cümle aranır: ham bulgunun yönergeye kopyalanması yetmez,
    # kurtarma turu "şu dosyanın şu satırı" görevini almalı.
    assert "res://player.gd:12 konumunda" in karar.guidance
    assert "velocity" in karar.guidance


def test_tani_yoksa_yonerge_bozulmaz():
    dogrulama = StepVerificationResult(ok=False, evidence=(), findings=("dosya bulunamadı",))

    karar = choose_recovery(classify_failure(_Outcome(), dogrulama), _step(), attempts=1)

    assert karar.guidance
    assert "konumunda" not in karar.guidance

"""Keşif/yürütme ayrımı ve kanıta bağlı yeniden planlama regresyonları."""

from __future__ import annotations

import json

import pytest

from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanPhase,
    PlanStep,
    RetrySafety,
    StepStatus,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_parser import PlanParseError, parse_execution_plan
from fusion_cli.engines.agent.progress import progress_fingerprint
from fusion_cli.engines.agent.replan import merge_replanned_plan
from fusion_cli.engines.agent.step_verification import StepVerificationResult


def _step(
    step_id: str,
    *,
    phase: PlanPhase = PlanPhase.EXECUTION,
    target: str = "assets/player.png",
    depends_on: tuple[str, ...] = (),
    status: StepStatus = StepStatus.PENDING,
) -> PlanStep:
    criterion = f"{target} mevcut"
    return PlanStep(
        step_id=step_id,
        goal=f"{target} hazırla",
        depends_on=depends_on,
        expected_effects=() if phase is PlanPhase.DISCOVERY else (f"file:{target}",),
        allowed_tool_families=("files",),
        success_criteria=(criterion,),
        verification_hint="dosyayı denetle",
        retry_safety=RetrySafety.SAFE,
        status=status,
        phase=phase,
        verification_checks=(
            VerificationCheck(criterion, VerificationCheckKind.FILE_EXISTS, target),
        ),
    )


def test_kesif_adimi_henuz_bilinmeyen_dosya_uretimini_vaat_edemez():
    payload = {
        "plan_id": "p",
        "task": "asset bul",
        "steps": [
            {
                "step_id": "discover",
                "goal": "asset konumunu bul",
                "depends_on": [],
                "expected_effects": ["file:assets/player.png"],
                "allowed_tool_families": ["files", "web"],
                "success_criteria": ["asset bulundu"],
                "verification_hint": "dosyayı denetle",
                "verification_checks": [
                    {
                        "criterion_id": "asset bulundu",
                        "kind": "file_exists",
                        "target": "assets/player.png",
                        "expected": "",
                    }
                ],
                "retry_safety": "safe",
                "phase": "discovery",
            }
        ],
    }

    with pytest.raises(PlanParseError, match="Keşif adımı"):
        parse_execution_plan(json.dumps(payload))


def test_ilerleme_parmak_izi_model_anlatimindan_etkilenmez():
    step = _step("asset")
    verification = StepVerificationResult(ok=False, findings=("dosya bulunamadı",))
    first = AgentOutcome(
        final_text="birinci anlatım",
        messages=[],
        tool_uses=(ToolUse("read_file", False, False, {"path": "x"}, "yok"),),
    )
    second = AgentOutcome(
        final_text="tamamen farklı anlatım",
        messages=[],
        tool_uses=first.tool_uses,
    )

    assert progress_fingerprint(step, first, verification) == progress_fingerprint(
        step, second, verification
    )


def test_yeniden_planlama_tamamlanan_kesfi_korur_ve_hedefi_degistirir():
    current = ExecutionPlan(
        "p",
        "oyun yap",
        (
            _step(
                "discover", phase=PlanPhase.DISCOVERY, target="repo", status=StepStatus.COMPLETED
            ),
            _step("asset", target="assets/missing.png", depends_on=("discover",)),
        ),
    )
    candidate = ExecutionPlan(
        "aday",
        "oyun yap",
        (_step("asset-real", target="game/assets/player.png", depends_on=("discover",)),),
    )

    merged = merge_replanned_plan(current, candidate, "asset", "fp-1")

    assert merged is not None
    assert merged.steps[0] == current.steps[0]
    assert merged.steps[1].step_id == "asset-real"
    assert merged.steps[1].revision == 1
    assert merged.steps[1].last_progress_fingerprint == "fp-1"


def test_ayni_hedefi_ureten_yeniden_plan_reddedilir():
    failed = _step("asset", target="assets/missing.png")
    current = ExecutionPlan("p", "oyun yap", (failed,))
    candidate = ExecutionPlan("aday", "oyun yap", (failed,))

    assert merge_replanned_plan(current, candidate, "asset", "fp") is None


def test_yeniden_plan_bagimsiz_bekleyen_teslimati_dusuremez():
    pending = _step("story", target="story.json")
    current = ExecutionPlan(
        "p", "hikayeli oyun", (_step("asset", target="missing.png"), pending)
    )
    candidate = ExecutionPlan("aday", "oyun", (_step("new-asset", target="player.png"),))

    merged = merge_replanned_plan(current, candidate, "asset", "fp")

    assert merged is not None
    assert pending in merged.steps

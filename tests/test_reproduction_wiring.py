"""Reprodüksiyon kontrolü adım doğrulamasından geçer.

Kanıt türü tek başına yetmez: plan bir reprodüksiyon kontrolü bildirdiğinde adım
doğrulaması onu değerlendirmeli ve "önce kırmızı" görülmediyse adımı doğrulanmış
saymamalı.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from fusion_cli.core.evidence import EvidenceStatus, ToolUse
from fusion_cli.core.execution_plan import (
    PlanStep,
    RetrySafety,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.step_verification import verify_step

KOMUT = "python -m pytest -q test_ortalama.py"


def _step() -> PlanStep:
    return PlanStep(
        step_id="duzelt",
        goal="hatayı düzelt",
        depends_on=(),
        expected_effects=(),
        allowed_tool_families=("files", "shell"),
        success_criteria=("hata düzeltildi",),
        verification_hint=KOMUT,
        retry_safety=RetrySafety.SAFE,
        verification_checks=(
            VerificationCheck("hata düzeltildi", VerificationCheckKind.REPRODUCTION, KOMUT),
        ),
    )


def _deps(tmp_path):
    return SimpleNamespace(
        tool_context=ToolContext(root=tmp_path), verifier=None, execution=None, budget=None
    )


def _use(ok: bool) -> ToolUse:
    return ToolUse(name="run_shell", ok=ok, mutating=False, arguments={"command": KOMUT}, output="")


async def test_once_kirmizi_sonra_yesil_adimi_dogrular(tmp_path):
    outcome = AgentOutcome(
        final_text="düzeltildi", messages=[], tool_uses=(_use(False), _use(True)), tool_calls_made=2
    )

    sonuc = await verify_step(_step(), outcome, _deps(tmp_path))

    kanit = next(item for item in sonuc.criteria if item.criterion_id == "hata düzeltildi")
    assert kanit.status is EvidenceStatus.PASSED
    assert sonuc.ok


async def test_yalniz_yesil_adimi_dogrulanmis_yapmaz(tmp_path):
    outcome = AgentOutcome(
        final_text="düzeltildi", messages=[], tool_uses=(_use(True),), tool_calls_made=1
    )

    sonuc = await verify_step(_step(), outcome, _deps(tmp_path))

    kanit = next(item for item in sonuc.criteria if item.criterion_id == "hata düzeltildi")
    assert kanit.status is EvidenceStatus.UNVERIFIED
    assert sonuc.unverified


async def test_hala_kirmizi_adimi_dusurur(tmp_path):
    outcome = AgentOutcome(
        final_text="denedim", messages=[], tool_uses=(_use(False),), tool_calls_made=1
    )

    sonuc = await verify_step(_step(), outcome, _deps(tmp_path))

    assert not sonuc.ok


async def test_eski_planlar_bozulmaz(tmp_path):
    """Reprodüksiyon kontrolü OLMAYAN plan eskisi gibi çalışmalı."""
    adim = replace(_step(), verification_checks=())
    outcome = AgentOutcome(final_text="tamam", messages=[], tool_calls_made=1)

    sonuc = await verify_step(adim, outcome, _deps(tmp_path))

    assert sonuc.ok or sonuc.unverified

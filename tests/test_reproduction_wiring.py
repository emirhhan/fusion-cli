"""Reprodüksiyon kontrolü adım doğrulamasından geçer.

Kanıt türü tek başına yetmez: plan bir reprodüksiyon kontrolü bildirdiğinde adım
doğrulaması onu değerlendirmeli ve "önce kırmızı" görülmediyse adımı doğrulanmış
saymamalı.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.core.checkpoint import StepCheckpointEvidence
from fusion_cli.core.evidence import EvidenceEnvironment, EvidenceStatus, ToolUse
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    RetrySafety,
    StepStatus,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.step_verification import verify_plan_acceptance, verify_step
from fusion_cli.engines.agent.turn_report import TurnReport, evidence_payload
from fusion_cli.memory.checkpoint_evidence import evidence_payload as checkpoint_payload
from fusion_cli.memory.checkpoint_evidence import parse_evidence

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
    return ToolUse(
        name="run_shell",
        ok=ok,
        mutating=False,
        arguments={"command": KOMUT},
        output="",
        source_digest="new" if ok else "old",
        source_after_digest="new" if ok else "old",
        environment=EvidenceEnvironment(KOMUT, "/repo", "python", "deps", "config"),
        call_id="green" if ok else "red",
    )


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


async def test_live_tool_records_call_and_source_after_approval(monkeypatch, tmp_path):
    import sys

    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.approval import Decision
    from fusion_cli.engines.agent.verify_discovery import source_digest
    from tests.fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from tests.test_agent_loop import _deps as loop_deps
    from tests.test_agent_loop import _kur

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")

    class ChangingPolicy:
        async def decide(self, request):
            source.write_text("value = 2\n")
            return Decision.ALLOW

    sink = RecordingSink()
    deps = loop_deps(tmp_path, sink)
    deps.policy = ChangingPolicy()
    call = tool_call("run_shell", command=f'{sys.executable} -c "print(42)"')
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=(call,)),
                model_result("İşlem tamamlandı; sonuç 42 olarak ölçüldü."),
            ]
        ),
    )
    outcome = await loop.run_agent("Komutu çalıştır ve sonucu açıkla.", deps)
    use = next(item for item in outcome.tool_uses if item.name == "run_shell")
    assert use.ok
    assert use.call_id == call.id
    assert use.source_digest == source_digest(tmp_path)
    assert use.source_after_digest == use.source_digest
    assert use.environment.cwd == str(tmp_path.resolve())


async def _measured_repro_run(root, command):
    from fusion_cli.engines.agent.verification import CommandVerifier

    result = await CommandVerifier((command,), cwd=str(root), timeout_s=10).verify()
    measured = result.evidence[0]
    return ToolUse(
        "run_shell",
        ok=result.ok,
        arguments={"command": command},
        output=measured.output,
        source_digest=measured.source_digest,
        source_after_digest=measured.source_after_digest,
        environment=measured.environment,
        call_id=measured.call_id,
    )


@pytest.mark.parametrize("case", ["fixed_bug", "initially_green", "literal_glob"])
async def test_real_pytest_reproduction_preserves_shell_selection(tmp_path, case):
    import sys

    from fusion_cli.core.execution_plan import ExecutionPlan, StepStatus
    from fusion_cli.engines.agent.reproduction import evaluate_reproduction
    from fusion_cli.engines.agent.step_verification import verify_plan_acceptance

    source = tmp_path / "app.py"
    source.write_text("value = 0\n" if case == "fixed_bug" else "value = 1\n")
    (tmp_path / "test_good.py").write_text(
        "from app import value\ndef test_value(): assert value == 1\n"
    )
    command = f"{sys.executable} -B -m pytest -q test_*.py"
    first = command.replace("test_*.py", "'test_*.py'") if case == "literal_glob" else command
    red = await _measured_repro_run(tmp_path, first)
    source.write_text("value = 1\n# ilgisiz not\n")
    green = await _measured_repro_run(tmp_path, command)
    assert green.ok
    assert red.ok is (case == "initially_green")
    if case == "literal_glob":
        assert "file or directory not found" in red.output
        assert "no tests ran" in red.output
    check = VerificationCheck("bug", VerificationCheckKind.REPRODUCTION, command)
    proof = evaluate_reproduction(check, tool_uses=(red, green))
    expected = EvidenceStatus.PASSED if case == "fixed_bug" else EvidenceStatus.UNVERIFIED
    assert proof.status is expected
    step = replace(
        _step(),
        status=StepStatus.COMPLETED,
        success_criteria=("bug",),
        verification_checks=(check,),
    )
    final = await verify_plan_acceptance(
        ExecutionPlan("p", "bugfix", (step,)), _deps(tmp_path), evidence=(proof,)
    )
    assert final.ok is (case == "fixed_bug")


@pytest.mark.parametrize("both_red", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
async def test_two_repro_targets_keep_checkpoint_and_final_identity(tmp_path, both_red, legacy):
    source = tmp_path / "app.py"
    source.write_text(f"first = {0 if both_red else 1}\nsecond = 0\n")
    (tmp_path / "test_first.py").write_text(
        "from app import first\ndef test_first(): assert first == 1\n"
    )
    (tmp_path / "test_second.py").write_text(
        "from app import second\ndef test_second(): assert second == 2000\n"
    )
    commands = tuple(
        f"{sys.executable} -B -m pytest -q test_{name}.py" for name in ("first", "second")
    )
    uses = [await _measured_repro_run(tmp_path, command) for command in commands]
    source.write_text("first = 1\nsecond = 2000\n")
    if both_red:
        uses.append(await _measured_repro_run(tmp_path, commands[0]))
    uses.append(await _measured_repro_run(tmp_path, commands[1]))
    assert [item.ok for item in uses] == (
        [False, False, True, True] if both_red else [True, False, True]
    )
    checks = tuple(
        VerificationCheck("all", VerificationCheckKind.REPRODUCTION, command)
        for command in commands
    )
    step = replace(
        _step(), status=StepStatus.COMPLETED, success_criteria=("all",), verification_checks=checks
    )
    checked = await verify_step(
        step, AgentOutcome("Ölçümler alındı.", [], tool_uses=tuple(uses)), _deps(tmp_path)
    )
    expected = [
        EvidenceStatus.PASSED if both_red else EvidenceStatus.UNVERIFIED,
        EvidenceStatus.PASSED,
    ]
    proofs = tuple(item for item in checked.criteria if item.criterion_id == "all")
    assert [item.status for item in proofs] == expected
    stored = checkpoint_payload(
        (StepCheckpointEvidence(step.step_id, criteria=checked.criteria, tool_uses=tuple(uses)),)
    )
    if legacy:
        for item in stored[0]["criteria"]:
            item.pop("check_target", None)
    loaded = parse_evidence(stored)
    final = await verify_plan_acceptance(
        ExecutionPlan("p", "iki düzeltme", (step,)), _deps(tmp_path), evidence=loaded[0].criteria
    )
    assert final.ok is both_red
    assert [item.status for item in final.evidence[-2:]] == expected
    assert [item.command for item in final.evidence[-2:]] == list(commands)
    assert [item.check_target for item in final.evidence[-2:]] == list(commands)
    assert [item.check_expected for item in final.evidence[-2:]] == ["", ""]
    projected = tuple(item for item in final.evidence if item.criterion_id == "all")
    payload = evidence_payload(TurnReport(criteria=projected, gate=final))
    assert payload["criteria_count"] == 1
    assert payload["criteria"][0]["status"] == ("passed" if both_red else "unverified")

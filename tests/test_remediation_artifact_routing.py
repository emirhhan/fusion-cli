"""Ekran görüntüsü saklanır; kod incelemesi ve kod testi diye yönlendirilmez."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import teacher_flow
from fusion_cli.engines.agent.turn_report import TurnReport
from tests.fakes import RecordingSink
from tests.test_agent_loop import _deps


@pytest.mark.asyncio
async def test_screenshot_only_change_does_not_call_code_teacher(tmp_path, monkeypatch):
    context = ToolContext(root=tmp_path)
    screenshot = tmp_path / "screen.png"
    context.changes.record(screenshot)
    screenshot.write_bytes(b"\x89PNG\x00artifact")
    deps = SimpleNamespace(tool_context=context)
    monkeypatch.setattr(teacher_flow, "teacher_is_ready", lambda *_: True)

    async def code_teacher(*args, **kwargs):
        pytest.fail("Görsel çıktı boş kod farkıyla öğretmene gönderildi")

    monkeypatch.setattr(teacher_flow, "_ask", code_teacher)
    assert (
        await teacher_flow.review_teacher_changes(
            "Ekran görüntüsü al", SimpleNamespace(ok=True, tool_uses=()), deps, None
        )
        is None
    )
    assert context.changes.paths == (screenshot,)


def test_screenshot_report_does_not_require_code_test_command():
    report = TurnReport(changed_paths=(".fusion/tmp/screen.png",))
    text = report.render()
    assert "doğrulama komutu" not in text
    assert "görsel" in text.lower()
    assert report.is_verified is False


@pytest.mark.asyncio
async def test_screenshot_route_opens_artifact_without_running_code_gate(tmp_path):
    from PIL import Image

    from fusion_cli.engines.agent.loop import AgentOutcome, _new_budget, _verify

    deps = _deps(tmp_path, RecordingSink())
    deps.budget = _new_budget(deps.config)
    context = deps.tool_context
    screenshot = tmp_path / "screen.png"
    context.changes.record(screenshot)
    Image.new("RGB", (8, 8), "red").save(screenshot)

    from fusion_cli.engines.agent.artifact_verify import ArtifactChangeVerifier
    from fusion_cli.engines.agent.verification import CommandVerifier, CompositeVerifier

    code_gate = CommandVerifier(
        ("this-command-must-not-exist",), cwd=str(tmp_path), timeout_s=1, tool_context=context
    )
    deps.verifier = CompositeVerifier((code_gate, ArtifactChangeVerifier(context)))
    outcome = AgentOutcome("", [], mutating_tool_calls_made=1)
    result = await _verify(outcome, deps, plan_mode=False, depth=0)
    assert result.ok
    assert result.evidence[0].status.value == "unverified"
    assert screenshot.exists()


@pytest.mark.asyncio
async def test_artifact_route_preserves_requested_output_gate(tmp_path):
    from PIL import Image

    from fusion_cli.engines.agent.loop import AgentOutcome, _new_budget, _verify
    from fusion_cli.engines.agent.output_verify import OutputPathVerifier

    deps = _deps(tmp_path, RecordingSink())
    deps.budget = _new_budget(deps.config)
    context = deps.tool_context
    screenshot = tmp_path / "screen.png"
    context.changes.record(screenshot)
    Image.new("RGB", (8, 8), "red").save(screenshot)
    context.requested_outputs.add("report.pdf")
    deps.verifier = OutputPathVerifier(context)
    result = await _verify(
        AgentOutcome("", [], mutating_tool_calls_made=1), deps, plan_mode=False, depth=0
    )
    assert not result.ok
    assert any("report.pdf" in finding for finding in result.findings)

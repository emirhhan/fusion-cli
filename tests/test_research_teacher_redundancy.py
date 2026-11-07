"""Kaynak ve dosya kapısı geçmiş kısa rapora ikinci otomatik denetim gerekmez."""

from __future__ import annotations

import pytest

from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheckKind
from fusion_cli.core.research_grounding import GroundingVerdict
from fusion_cli.core.tools import ToolResult
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import teacher_flow
from fusion_cli.engines.agent.loop import AgentOutcome, _new_budget

from .test_teacher_auto_phase_budget import Registry
from .test_teacher_first import _setup

TASK = "https://example.org/releases/ sayfasını oku ve kısa bir raporu rapor.html olarak hazırla."


@pytest.mark.parametrize(
    "case", ["passed", "missing", "incomplete", "mechanical_fail", "explicit", "stale"]
)
async def test_only_current_successful_bounded_report_skips_extra_automatic_teacher(
    monkeypatch, tmp_path, case
):
    deps, *_ = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(teacher_flow, "teacher_is_ready", lambda *_args: True)
    deps.budget = budget = _new_budget(deps.config)
    budget.research_required = True
    budget.research_verdict = GroundingVerdict("target-digest", "source-digest", "supported")
    path = tmp_path / "rapor.html"
    path.write_text("<p>Source-backed report.</p>")
    deps.tool_context.changes.record(path)
    status = EvidenceStatus.UNVERIFIED if case == "incomplete" else EvidenceStatus.PASSED
    evidence = (
        ()
        if case == "missing"
        else (
            CriterionEvidence(
                "research_grounding",
                VerificationCheckKind.TOOL,
                status,
                "Source check.",
                source_digest="old-digest" if case == "stale" else "target-digest",
                source_after_digest="source-digest",
            ),
        )
    )
    verification = VerificationResult(ok=case != "mechanical_fail", evidence=evidence)
    registry = Registry([ToolResult('{"bulgular":[]}')], delay=0)
    task = TASK + (" Önce öğretmene danış." if case == "explicit" else "")
    await teacher_flow.review_teacher_changes(
        task, AgentOutcome("Rapor hazır.", []), deps, registry, verification=verification
    )
    assert registry.calls == (0 if case == "passed" else 1)


async def test_teacher_findings_are_rechecked_after_the_repaired_source_gate_passes(
    monkeypatch, tmp_path
):
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools import web

    from .fakes import model_result, tool_call
    from .test_research_grounding import typed_clean

    deps, _, teacher, _ = _setup(
        monkeypatch,
        tmp_path,
        teacher_answers=[
            model_result('{"bulgular":["Missing caption"]}'),
            model_result('{"bulgular":[]}'),
        ],
        apprentice_answers=[
            model_result(tool_calls=[tool_call("web_fetch", url="https://example.org/releases/")]),
            model_result(
                tool_calls=[tool_call("write_file", path="rapor.html", content="<p>Report.</p>")]
            ),
            model_result("Rapor dosyası: rapor.html."),
            model_result(
                tool_calls=[
                    tool_call(
                        "write_file", path="rapor.html", content="<p>Report with caption.</p>"
                    )
                ]
            ),
            model_result("Rapor düzeltildi: rapor.html."),
        ],
    )
    monkeypatch.setattr(teacher_flow, "teacher_is_ready", lambda *_args: True)
    monkeypatch.setattr(loop, "MAX_VERIFY_ROUNDS", 0)
    monkeypatch.setattr(web, "url_block_reason", lambda *_: None)
    monkeypatch.setattr(
        web,
        "fetch_following_redirects",
        lambda url: ("text/html", "<p>Source-backed report with caption.</p>", url),
    )

    async def judge(prompt, *args, **options):
        return model_result(typed_clean(prompt))

    monkeypatch.setattr(loop.review, "_ask", judge)

    class FileVerifier:
        async def verify(self):
            repaired = "caption" in (tmp_path / "rapor.html").read_text()
            return VerificationResult(
                ok=repaired,
                summary="Report file checked.",
                findings=() if repaired else ("Missing caption",),
            )

    deps.verifier = FileVerifier()
    result = await loop.run_agent(TASK, deps, self_review=False)
    assert result.ok
    assert teacher.calls == 2
    assert "caption" in (tmp_path / "rapor.html").read_text()

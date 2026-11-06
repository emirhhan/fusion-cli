"""Offline source-consistency regressions through the real actor/reader boundary."""

from __future__ import annotations

import pytest

from fusion_cli.core.events import VerificationPassed
from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.tools import web

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur

PAGES = {
    "index": (
        "<h1>Orion release index</h1><p>Latest stable: 8.4.2. Older branches: 7.9.6 and 6.8.4.</p>"
    ),
    "release": (
        "<h1>Orion 8.4.2</h1><p>Release date: 2031-10-25. No release time or timezone "
        "is specified.</p>"
    ),
    "announcement": (
        '<meta property="article:published_time" content="2031-10-26"><p>Orion 8.4.2 '
        "announcement published October 26.</p>"
    ),
    "lifecycle": (
        "<h1>Support</h1><p>Orion 6 support ends 2032-04. Orion 7 support ends 2033-10.</p>"
    ),
    "prerelease": (
        "<h1>Prereleases</h1><p>Orion 9.0.0a1 is a prerelease; Orion 9 final is planned"
        " for 2032-10.</p>"
    ),
}
GOOD = (
    "<html><body><h1>Orion</h1><p>Latest stable 8.4.2; released "
    "2031-10-25.</p><table><tr><td>7 latest 7.9.6; 6 EOL "
    "2032-04.</td></tr></table><p>9.0.0a1 is a prerelease, final planned "
    "2032-10.</p></body></html>"
)
BAD = (
    "<html><body><h1>Orion</h1><p>Latest stable 8.4.2; released 2031-10-26 at 03:00 "
    "Istanbul.</p><table><tr><td>7 latest 7.9.1; 6 EOL "
    "2030-04.</td></tr></table><p>Orion 10 final planned 2032-10.</p></body></html>"
)
TASK = (
    "Research Orion official sources; write report.html with latest stable, release "
    "date, older branches, support and requested prerelease distinction."
)


async def run_report(monkeypatch, tmp_path, *, supported, typed_judge=None, repair=False):
    sink = RecordingSink()
    reads = list(PAGES) if supported else ["index", "announcement"]
    calls = [
        model_result(tool_calls=[tool_call("web_fetch", url=f"https://orion.example/{name}")])
        for name in reads
    ]
    calls += [
        model_result(
            tool_calls=[
                tool_call("write_file", path="report.html", content=GOOD if supported else BAD)
            ]
        ),
        model_result("Rapor hazır: `report.html`. İstenen araştırma tamamlandı."),
    ]
    if repair:
        calls += [
            model_result(tool_calls=[tool_call("web_fetch", url=f"https://orion.example/{name}")])
            for name in ("release", "lifecycle", "prerelease")
        ]
        calls += [
            model_result(tool_calls=[tool_call("write_file", path="report.html", content=GOOD)]),
            model_result("Rapor düzeltildi: `report.html`."),
        ]
    _kur(monkeypatch, ScriptedProvider(calls))
    monkeypatch.setattr(web, "url_block_reason", lambda url: None)
    monkeypatch.setattr(
        web,
        "fetch_following_redirects",
        lambda url: ("text/html", PAGES[url.rsplit("/", 1)[-1]], url),
    )

    async def judge(prompt, config, publisher):
        return model_result(typed_judge(prompt) if typed_judge else "TAMAM")

    monkeypatch.setattr(loop.review, "_ask", judge)
    deps = _deps(tmp_path, sink, runtime={"self_review": True, "agent_max_steps": 30})
    deps.execution = ExecutionPolicy(
        is_web=False, requires_web_lookup=True, heuristic_auto_continue=False
    )

    class FileVerifier:
        async def verify(self):
            assert (tmp_path / "report.html").read_text() in (GOOD, BAD)
            return VerificationResult(ok=True, summary="HTML file checks passed")

    deps.verifier = FileVerifier()
    result = await loop.run_agent(TASK, deps)
    return result, deps, sink


async def test_supported_report_baseline_control(monkeypatch, tmp_path):
    result, _, _ = await run_report(monkeypatch, tmp_path, supported=True, typed_judge=typed_clean)
    assert result.ok
    assert "report.html" in result.final_text
    assert (tmp_path / "report.html").read_text() == GOOD


async def test_untyped_clean_review_cannot_verify_researched_report(monkeypatch, tmp_path):
    result, _deps_used, sink = await run_report(monkeypatch, tmp_path, supported=False)
    gate = result.completion_report.gate if result.completion_report else None
    criterion = (
        next((item for item in gate.evidence if item.criterion_id == "research_grounding"), None)
        if gate
        else None
    )
    assert criterion is not None, (
        "required factual criterion missing after real reader + write + green file verifier"
    )
    assert criterion.status in (EvidenceStatus.FAILED, EvidenceStatus.UNVERIFIED)
    assert not result.ok
    assert "report.html" in result.final_text
    assert not any(isinstance(event, VerificationPassed) for event in sink.events)


def typed_clean(prompt):
    import json

    payload = json.loads(prompt.split("\nDATA\n", 1)[1])
    return json.dumps(
        {
            "target_digest": payload["target_digest"],
            "source_digest": payload["source_digest"],
            "status": "supported",
            "reviewed": list(payload["target"]),
            "claims": [
                {
                    "targets": list(payload["target"]),
                    "kind": "supported",
                    "sources": [next(iter(payload["sources"][0]["spans"]))],
                    "basis": (
                        "Release event, branch/support table and requested prerelease "
                        "distinction checked against read documents."
                    ),
                }
            ],
        }
    )


async def test_supported_typed_report_has_required_pass(monkeypatch, tmp_path):
    result, _deps_used, _ = await run_report(
        monkeypatch, tmp_path, supported=True, typed_judge=typed_clean
    )
    gate = result.completion_report.gate
    assert result.ok
    assert (
        next(item for item in gate.evidence if item.criterion_id == "research_grounding").status
        is EvidenceStatus.PASSED
    )


def test_web_fetch_produces_private_exact_reader_receipt(monkeypatch, tmp_path):
    from fusion_cli.core.tools import ToolContext

    monkeypatch.setattr(web, "url_block_reason", lambda url: None)
    monkeypatch.setattr(
        web,
        "fetch_following_redirects",
        lambda url: ("text/html", PAGES["announcement"], "https://orion.example/final"),
    )
    result = web.web_fetch(
        {"url": "https://orion.example/announcement"}, ToolContext(root=tmp_path)
    )
    receipt = getattr(result, "source_receipt", None)
    assert receipt is not None
    assert receipt.text in result.output
    assert receipt.final_url.endswith("/final")
    assert receipt.published_at == "2031-10-26"
    assert receipt.completeness == "complete"
    assert "source_receipt" not in result.structured


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_source",
        "target_digest",
        "source_digest",
        "missing_coverage",
        "empty_claims",
        "bad_target",
        "free_text",
        "incomplete",
    ],
)
def test_typed_verdict_rejects_unbound_or_uncovered_claims(tmp_path, mutation):
    import json

    from fusion_cli.core.research_grounding import SourceReceipt
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract
    from fusion_cli.engines.agent.research_grounding import (
        capture_source,
        parse_verdict,
        snapshot_target,
    )

    context = ToolContext(root=tmp_path)
    contract = accept_delivery_contract(context, "Research Orion")
    target = snapshot_target(context, "Orion 8 released October 25.")
    source = capture_source(
        SourceReceipt(
            "https://orion.example/",
            "https://orion.example/",
            "2031-10-26",
            "Orion 8 released October 25.",
        ),
        contract,
        "read1",
    )
    from fusion_cli.engines.agent.research_grounding import request_payload

    payload = request_payload(target, (source,))
    raw = json.loads(typed_clean("\nDATA\n" + json.dumps(payload)))
    if mutation == "unknown_source":
        raw["claims"][0]["sources"] = ["forged:1"]
    if mutation in ("target_digest", "source_digest"):
        raw[mutation] = "forged"
    if mutation == "missing_coverage":
        raw["reviewed"] = []
    if mutation == "empty_claims":
        raw["claims"] = []
    if mutation == "bad_target":
        raw["claims"][0]["targets"] = ["unknown"]
    if mutation == "incomplete":
        raw["status"] = "incomplete"
    verdict = parse_verdict(
        "TAMAM" if mutation == "free_text" else json.dumps(raw), target, (source,)
    )
    assert verdict.status == "incomplete"


def typed_issues(prompt):
    import json

    raw = json.loads(typed_clean(prompt))
    raw["status"] = "issues"
    raw["claims"][0]["kind"] = "date_role"
    raw["claims"][0]["basis"] = (
        "Announcement publication is not release date; table branch/EOL, unread next-series "
        "schedule and timezone lack read support. Preserve requested prerelease distinction."
    )
    return json.dumps(raw)


async def test_real_report_contradictions_reach_bounded_correction(monkeypatch, tmp_path):
    # Leave bad bytes untouched: a CSS/no-edit explanation cannot make findings disappear.
    result, deps, sink = await run_report(
        monkeypatch, tmp_path, supported=False, typed_judge=typed_issues
    )
    from fusion_cli.core.events import VerificationFailed

    failures = [event for event in sink.events if isinstance(event, VerificationFailed)]
    assert failures
    assert "report.html" in " ".join(failures[0].findings)
    assert "publication" in " ".join(failures[0].findings)
    assert deps.require_budget().verify_rounds <= deps.require_budget().max_verify_rounds
    assert not result.ok
    assert "report.html" in result.final_text
    assert (tmp_path / "report.html").read_text() == BAD


@pytest.mark.parametrize("mode", ["error", "truncated", "empty"])
async def test_judge_measurement_failure_is_unverified_without_repair(monkeypatch, tmp_path, mode):
    def fail(prompt):
        if mode == "error":
            raise RuntimeError("fixture judge unavailable")
        return "" if mode == "empty" else "{"

    result, deps, _ = await run_report(monkeypatch, tmp_path, supported=True, typed_judge=fail)
    assert not result.ok
    assert deps.require_budget().verify_rounds == 0
    assert "report.html" in result.final_text
    assert result.final_text.count("Olgusal kaynak denetimi tamamlanamadı.") == 1


@pytest.mark.parametrize("chat_mode", [False, True])
async def test_text_only_research_corrects_without_forced_workspace_write(
    monkeypatch, tmp_path, chat_mode
):
    import json

    sink = RecordingSink()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("web_fetch", url="https://orion.example/release")]
                ),
                model_result("Orion released October 26."),
                model_result("Orion released October 25; the source gives no time or timezone."),
            ]
        ),
    )
    monkeypatch.setattr(web, "url_block_reason", lambda url: None)
    monkeypatch.setattr(
        web, "fetch_following_redirects", lambda url: ("text/html", PAGES["release"], url)
    )

    async def judge(prompt, config, publisher):
        data = json.loads(prompt.split("\nDATA\n")[1])
        text = " ".join(row["text"] for row in data["target"].values())
        return model_result(typed_issues(prompt) if "October 26" in text else typed_clean(prompt))

    monkeypatch.setattr(loop.review, "_ask", judge)
    deps = _deps(tmp_path, sink)
    deps.execution = ExecutionPolicy(
        is_web=False, requires_web_lookup=True, heuristic_auto_continue=False
    )
    result = await loop.run_agent("Research Orion release date", deps, chat_mode=chat_mode)
    assert result.ok
    assert "October 25" in result.final_text
    assert result.mutating_tool_calls_made == 0
    assert deps.require_budget().verify_rounds == 1
    assert not list(tmp_path.iterdir())


def target_sources(tmp_path, text="Orion released October 25."):
    from fusion_cli.core.research_grounding import SourceReceipt
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract
    from fusion_cli.engines.agent.research_grounding import capture_source, snapshot_target

    context = ToolContext(root=tmp_path)
    contract = accept_delivery_contract(context, "Research Orion")
    source = capture_source(
        SourceReceipt(
            "https://orion.example/",
            "https://orion.example/",
            "2031-10-26",
            "Orion released October 25.",
        ),
        contract,
        "read1",
    )
    return context, snapshot_target(context, text), (source,)


@pytest.mark.parametrize("field", ["accepted_id", "root", "owner"])
def test_other_task_owner_sources_are_not_admitted(tmp_path, field):
    from dataclasses import replace

    from fusion_cli.engines.agent.research_grounding import request_payload

    _, target, sources = target_sources(tmp_path)
    payload = request_payload(target, (replace(sources[0], **{field: "other"}),))
    assert payload["sources"] == []
    assert payload["omitted_sources"] == 1


@pytest.mark.parametrize("change", ["answer", "file", "sources", "css"])
async def test_final_snapshot_changes_invalidate_cached_review(monkeypatch, tmp_path, change):
    from dataclasses import replace

    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.research_grounding import finalize_grounding, snapshot_target

    context, _, sources = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context = context
    budget = deps.require_budget() if deps.budget else loop._new_budget(deps.config)
    deps.budget = budget
    budget.research_required = True
    budget.research_contract = context.delivery_contract.accepted
    budget.research_sources.extend(sources)
    calls = []

    async def judge(prompt, config, publisher):
        calls.append(prompt)
        return model_result(typed_clean(prompt))

    monkeypatch.setattr(loop.review, "_ask", judge)
    path = tmp_path / "report.html"
    path.write_text(GOOD)
    context.requested_outputs.add("report.html")
    outcome = AgentOutcome("Rapor `report.html`.", [])
    gate = await finalize_grounding(outcome, deps, VerificationResult(ok=True))
    assert gate.ok
    await finalize_grounding(outcome, deps, VerificationResult(ok=True))
    assert len(calls) == 1
    if change == "answer":
        outcome.final_text += " Added claim."
    elif change == "sources":
        budget.research_sources.append(replace(sources[0], call_id="read2"))
    else:
        path.write_text(GOOD + ("<style>p{color:red}</style>" if change == "css" else "new claim"))
    gate = await finalize_grounding(outcome, deps, VerificationResult(ok=True))
    assert len(calls) == 2
    assert gate.evidence[-1].source_digest == snapshot_target(context, outcome.final_text).digest


async def test_oversized_complete_context_is_not_prefix_reviewed(monkeypatch, tmp_path):
    from fusion_cli.engines.agent.research_grounding import review_grounding

    _, target, sources = target_sources(tmp_path, "fact " * 15000)
    deps = _deps(tmp_path, RecordingSink())

    async def forbidden(prompt):
        raise AssertionError("must not call judge with clipped target")

    verdict = await review_grounding(target, sources, deps, judge=forbidden)
    assert verdict.status == "incomplete"


def test_unextractable_required_artifact_is_incomplete(tmp_path):
    from fusion_cli.engines.agent.research_grounding import snapshot_target

    context, _, _ = target_sources(tmp_path)
    context.requested_outputs.add("report.pdf")
    (tmp_path / "report.pdf").write_bytes(b"%PDF")
    assert not snapshot_target(context, "Report ready.").complete


def test_public_tool_and_history_output_never_contain_private_receipt(monkeypatch, tmp_path):
    import json

    from fusion_cli.core.tools import ToolContext

    monkeypatch.setattr(web, "url_block_reason", lambda url: None)
    monkeypatch.setattr(
        web, "fetch_following_redirects", lambda url: ("text/html", PAGES["index"], url)
    )
    result = web.web_fetch({"url": "https://orion.example/index"}, ToolContext(root=tmp_path))
    assert "source_receipt" not in json.dumps(result.structured)
    assert "accepted_id" not in result.output


@pytest.mark.parametrize("supported", [True, False])
async def test_workflow_finalization_requires_same_grounding_even_without_self_review(
    monkeypatch, tmp_path, supported
):
    from fusion_cli.core.execution_plan import (
        ExecutionPlan,
        PlanStep,
        RetrySafety,
        VerificationCheck,
        VerificationCheckKind,
    )
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.plan_runner import run_execution_plan

    context, _, sources = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context = context
    deps.budget = loop._new_budget(deps.config)
    deps.budget.research_required = True
    deps.budget.research_contract = context.delivery_contract.accepted
    deps.budget.research_sources.extend(sources)
    deps.budget.max_verify_rounds = 0

    async def judge(prompt, config, publisher):
        return model_result(typed_clean(prompt) if supported else typed_issues(prompt))

    monkeypatch.setattr(loop.review, "_ask", judge)

    async def actor(task, deps, **kwargs):
        return AgentOutcome(
            "Orion released October 25." if supported else "Orion released October 26.",
            [],
            model_calls_made=1,
        )

    (tmp_path / "report.html").write_text(GOOD if supported else BAD)
    context.requested_outputs.add("report.html")
    plan = ExecutionPlan(
        "research",
        "Research Orion",
        (
            PlanStep(
                "report",
                "Research Orion",
                depends_on=(),
                expected_effects=(),
                allowed_tool_families=("web",),
                success_criteria=("report exists",),
                verification_checks=(
                    VerificationCheck(
                        "report exists", VerificationCheckKind.FILE_EXISTS, "report.html"
                    ),
                ),
                verification_hint="",
                retry_safety=RetrySafety.SAFE,
            ),
        ),
    )
    result = await run_execution_plan("Research Orion", deps, actor, plan=plan, self_review=False)
    assert result.ok is supported
    assert result.completion_report is not None
    factual = next(
        item
        for item in result.completion_report.gate.evidence
        if item.criterion_id == "research_grounding"
    )
    assert factual.status is (EvidenceStatus.PASSED if supported else EvidenceStatus.FAILED)


async def test_repaired_report_retains_requested_prerelease_and_original_delivery(
    monkeypatch, tmp_path
):
    import json

    from fusion_cli.core.events import VerificationFailed

    def judge(prompt):
        data = json.loads(prompt.split("\nDATA\n")[1])
        text = " ".join(span["text"] for span in data["target"].values())
        return typed_issues(prompt) if "03:00 Istanbul" in text else typed_clean(prompt)

    result, deps, sink = await run_report(
        monkeypatch, tmp_path, supported=False, typed_judge=judge, repair=True
    )
    assert result.ok
    assert (tmp_path / "report.html").read_text() == GOOD
    assert "9.0.0a1 is a prerelease" in GOOD
    assert "report.html" in result.final_text
    assert deps.require_budget().verify_rounds == 1
    assert len({s.accepted_id for s in deps.require_budget().research_sources}) == 1
    assert any(isinstance(event, VerificationFailed) for event in sink.events)
    assert result.completion_report.gate.evidence[-1].status is EvidenceStatus.PASSED


async def test_receipts_are_not_rehydrated_from_previous_task_history(monkeypatch, tmp_path):
    result, deps, _ = await run_report(
        monkeypatch, tmp_path, supported=True, typed_judge=typed_clean
    )
    old_id = deps.require_budget().research_sources[0].accepted_id
    _kur(monkeypatch, ScriptedProvider([model_result("Yeni görev için tarih belirlenemedi.")]))
    deps.execution = ExecutionPolicy(
        is_web=False, requires_web_lookup=True, heuristic_auto_continue=False
    )
    second = await loop.run_agent("Research a different Orion fact", deps, history=result.messages)
    assert deps.require_budget().research_sources == []
    assert deps.require_budget().research_contract.accepted_id != old_id
    assert not second.ok


@pytest.mark.parametrize(
    "scope,completeness",
    [("controls", "complete"), ("document", "blocked"), ("document", "unknown")],
)
def test_controls_and_unavailable_sources_never_admit_body_evidence(tmp_path, scope, completeness):
    from dataclasses import replace

    from fusion_cli.engines.agent.research_grounding import request_payload

    _, target, sources = target_sources(tmp_path)
    receipt = replace(sources[0].receipt, scope=scope, completeness=completeness)
    payload = request_payload(target, (replace(sources[0], receipt=receipt),))
    assert payload["sources"] == []


@pytest.mark.parametrize(
    "kind", ["unsupported", "contradicted", "date_role", "coverage", "unread_citation"]
)
def test_typed_source_consistency_issue_kinds_are_blocking(tmp_path, kind):
    import json

    from fusion_cli.engines.agent.research_grounding import (
        as_verification,
        parse_verdict,
        request_payload,
    )

    _, target, sources = target_sources(tmp_path)
    raw = json.loads(typed_issues("\nDATA\n" + json.dumps(request_payload(target, sources))))
    raw["claims"][0]["kind"] = kind
    verdict = parse_verdict(json.dumps(raw), target, sources)
    assert verdict.status == "issues"
    evidence = as_verification(verdict, target)
    assert not evidence.ok
    assert evidence.evidence[0].status is EvidenceStatus.FAILED
    assert kind in evidence.findings[0]


async def test_public_events_and_model_requests_do_not_serialize_private_receipts(
    monkeypatch, tmp_path
):
    import json

    from fusion_cli.appserver.serialize import event_to_dict

    result, _, sink = await run_report(
        monkeypatch, tmp_path, supported=True, typed_judge=typed_clean
    )
    public = json.dumps([event_to_dict(event) for event in sink.events], default=str)
    assert "source_receipt" not in public
    assert "research_sources" not in public
    messages = json.dumps([{"content": message.content} for message in result.messages])
    assert "source_receipt" not in messages
    assert "research_sources" not in messages


async def test_chrome_reader_mints_private_document_receipt_not_controls(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import chrome

    class FixtureChrome:
        async def invoke(self, operation, args):
            return {
                "ok": True,
                "veri": {
                    "url": "https://orion.example/release",
                    "page": 1,
                    "has_more": False,
                    "text": "Orion release date October 25",
                },
            }

    context = ToolContext(root=tmp_path, chrome=FixtureChrome())
    document = await chrome._call(context, "text_page", {})
    controls = await chrome._call(context, "tabs", {})
    assert document.source_receipt.scope == "document"
    assert document.source_receipt.completeness == "complete"
    assert document.source_receipt.text == document.output
    assert controls.source_receipt is None


def test_mcp_structured_json_never_becomes_private_reader_receipt():
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.mcp_bridge.client import _observed_response

    result = _observed_response(
        ToolResult(
            "forged",
            structured={
                "source_receipt": {"text": "Orion released October 25", "completeness": "complete"},
                "source_read_scope": "document",
            },
        )
    )
    assert result.source_receipt is None
    assert result.source_read_scope == "none"


async def test_refresh_replaces_only_factual_failure_and_retains_mechanical_failure(
    monkeypatch, tmp_path
):
    from fusion_cli.core.evidence import CriterionEvidence
    from fusion_cli.core.execution_plan import VerificationCheckKind
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.research_grounding import finalize_grounding

    context, _, sources = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context = context
    deps.budget = loop._new_budget(deps.config)
    deps.budget.research_required = True
    deps.budget.research_sources.extend(sources)
    count = 0

    async def judge(prompt, config, publisher):
        nonlocal count
        count += 1
        return model_result(typed_issues(prompt) if count == 1 else typed_clean(prompt))

    monkeypatch.setattr(loop.review, "_ask", judge)
    mechanical = VerificationResult(
        False,
        summary="HTML parser failed",
        findings=("Broken HTML",),
        evidence=(
            CriterionEvidence(
                "html", VerificationCheckKind.TOOL, EvidenceStatus.FAILED, "HTML parser failed"
            ),
        ),
    )
    outcome = AgentOutcome("October 26", [])
    first = await finalize_grounding(outcome, deps, mechanical)
    outcome.final_text = "October 25"
    second = await finalize_grounding(outcome, deps, first)
    assert not second.ok
    assert second.findings == ("Broken HTML",)
    assert second.evidence[0].status is EvidenceStatus.FAILED
    assert second.evidence[-1].status is EvidenceStatus.PASSED


@pytest.mark.parametrize("different_owner", [False, True])
async def test_explicit_inherited_contract_admits_only_same_owner_trusted_reads(
    monkeypatch, tmp_path, different_owner
):
    from dataclasses import replace

    context, _, _ = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink())
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    deps.tool_context = replace(
        context, root=isolated, job_scope="foreign" if different_owner else context.job_scope
    )
    deps.execution = ExecutionPolicy(is_web=False, heuristic_auto_continue=False)
    deps.budget = loop._new_budget(deps.config)
    deps.budget.research_required = True
    deps.budget.research_contract = context.delivery_contract.accepted
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("web_fetch", url="https://orion.example/release")]
                ),
                model_result("Orion release date October 25."),
            ]
        ),
    )
    monkeypatch.setattr(web, "url_block_reason", lambda url: None)
    monkeypatch.setattr(
        web, "fetch_following_redirects", lambda url: ("text/html", PAGES["release"], url)
    )
    await loop.run_agent(
        "Read official Orion release", deps, depth=1, internal=True, verify=False, self_review=False
    )
    assert bool(deps.budget.research_sources) is (not different_owner)
    if not different_owner:
        assert deps.budget.research_sources[0].root == str(context.root.resolve())
        assert (
            deps.budget.research_sources[0].accepted_id
            == context.delivery_contract.accepted.accepted_id
        )


@pytest.mark.parametrize("foreign_contract", [False, True])
async def test_real_workflow_reader_requires_inherited_accepted_contract(
    monkeypatch, tmp_path, foreign_contract
):
    from dataclasses import replace

    from fusion_cli.core.delivery_contract import DeliveryContractState
    from fusion_cli.core.execution_plan import (
        ExecutionPlan,
        PlanStep,
        RetrySafety,
        VerificationCheck,
        VerificationCheckKind,
    )
    from fusion_cli.engines.agent.plan_runner import run_execution_plan

    context, _, _ = target_sources(tmp_path)
    context.requested_outputs.add("report.html")
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context = context
    deps.execution = ExecutionPolicy(
        is_web=False, requires_web_lookup=True, heuristic_auto_continue=False
    )
    deps.budget = loop._new_budget(deps.config)
    deps.budget.research_required = True
    deps.budget.research_contract = context.delivery_contract.accepted
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("web_fetch", url="https://orion.example/release")]
                ),
                model_result(
                    tool_calls=[
                        tool_call(
                            "write_file",
                            path="report.html",
                            content="<html><body>Orion release date: 2031-10-25.</body></html>",
                        )
                    ]
                ),
                model_result("Orion released 2031-10-25. Rapor: `report.html`."),
            ]
        ),
    )
    monkeypatch.setattr(web, "url_block_reason", lambda url: None)
    monkeypatch.setattr(
        web, "fetch_following_redirects", lambda url: ("text/html", PAGES["release"], url)
    )

    async def judge(prompt, config, publisher):
        return model_result(typed_clean(prompt))

    monkeypatch.setattr(loop.review, "_ask", judge)

    async def actor(task, child_deps, **kwargs):
        if foreign_contract:
            child_deps.tool_context = replace(
                child_deps.tool_context,
                delivery_contract=DeliveryContractState(
                    replace(context.delivery_contract.accepted, accepted_id="foreign-task")
                ),
            )
        return await loop.run_agent(task, child_deps, **kwargs)

    step = PlanStep(
        "report",
        "Read official release date and write report.html",
        depends_on=(),
        expected_effects=("file:report.html",),
        allowed_tool_families=("web", "files"),
        success_criteria=("report exists",),
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
        verification_checks=(
            VerificationCheck("report exists", VerificationCheckKind.FILE_EXISTS, "report.html"),
        ),
    )
    result = await run_execution_plan(
        "Research Orion release date in report.html",
        deps,
        actor,
        plan=ExecutionPlan("owned-research", "Research Orion", (step,)),
        self_review=False,
    )
    assert bool(deps.budget.research_sources) is (not foreign_contract)
    assert result.ok is (not foreign_contract), result.final_text
    assert "report.html" in result.final_text


def test_mechanical_failure_keeps_existing_mutating_correction_contract():
    from fusion_cli.core.evidence import CriterionEvidence
    from fusion_cli.core.execution_plan import VerificationCheckKind
    from fusion_cli.engines.agent.loop_contract import _verification_correction_task

    result = VerificationResult(
        False,
        summary="Broken HTML",
        findings=("Broken HTML",),
        evidence=(
            CriterionEvidence(
                "research_grounding",
                VerificationCheckKind.TOOL,
                EvidenceStatus.PASSED,
                "Kaynak tutarlılığı incelendi.",
            ),
        ),
    )
    correction = _verification_correction_task(result)
    assert "en az bir gerçek değiştirici araç" in correction


async def test_research_eligibility_is_bound_before_routine_workflow_dispatch(
    monkeypatch, tmp_path
):
    from fusion_cli.engines.agent import routine_invocation
    from fusion_cli.engines.agent.loop import AgentOutcome

    deps = _deps(tmp_path, RecordingSink())
    deps.execution = ExecutionPolicy(
        is_web=False, requires_web_lookup=True, heuristic_auto_continue=False
    )
    monkeypatch.setattr(routine_invocation, "selected_routine", lambda *args: (object(), "Orion"))

    async def planned(task, planned_deps, actor, **kwargs):
        assert planned_deps.require_budget().research_required
        assert planned_deps.require_budget().research_contract.task == "Research Orion"
        return AgentOutcome("routine delivery", [])

    monkeypatch.setattr(loop, "run_execution_plan", planned)
    await loop.run_agent("Research Orion", deps)


@pytest.mark.parametrize("replacement", [None, "Document contents withheld by hook."])
async def test_real_reader_receipt_requires_final_actor_visible_body(
    monkeypatch, tmp_path, replacement
):
    import json

    from fusion_cli.engines.agent.hook_bridge import ToolNote

    sink = RecordingSink()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("web_fetch", url="https://orion.example/release")]
                ),
                model_result("Kaynak araştırması tamamlandı."),
            ]
        ),
    )
    monkeypatch.setattr(web, "url_block_reason", lambda url: None)
    monkeypatch.setattr(
        web, "fetch_following_redirects", lambda url: ("text/html", PAGES["release"], url)
    )

    async def post_hook(*args, **kwargs):
        return ToolNote(replaced_output=replacement)

    payloads = []

    async def judge(prompt, config, publisher):
        payloads.append(json.loads(prompt.split("\nDATA\n", 1)[1]))
        return model_result(typed_clean(prompt) if replacement is None else "TAMAM")

    monkeypatch.setattr(loop, "post_tool_use", post_hook)
    monkeypatch.setattr(loop.review, "_ask", judge)
    deps = _deps(tmp_path, sink)
    deps.execution = ExecutionPolicy(
        is_web=False, requires_web_lookup=True, heuristic_auto_continue=False
    )
    result = await loop.run_agent("Research Orion release date", deps)
    message = next(message for message in result.messages if message.role == "tool")
    budget = deps.require_budget()
    # Real execution remains operation evidence even if its body is withheld.
    assert any(name == "web_fetch" for name, _, _ in budget.successful_tool_evidence)
    assert any(observation.tool_name == "web_fetch" for observation in budget.data_observations)
    assert payloads
    if replacement is None:
        assert "Release date: 2031-10-25" in message.content
        assert len(budget.research_sources) == 1
        assert "Release date: 2031-10-25" in budget.research_sources[0].receipt.text
        assert payloads[0]["sources"]
        assert result.ok
    else:
        assert message.content == replacement
        assert budget.research_sources == []
        assert payloads[0]["sources"] == []
        assert "Release date: 2031-10-25" not in json.dumps(payloads)
        assert not result.ok


async def test_rendered_grounding_schema_uses_exact_validator_enum_tokens(tmp_path):
    import re

    from fusion_cli.engines.agent.research_grounding import KINDS, review_grounding

    _, target, sources = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink())
    prompts = []

    async def judge(prompt):
        prompts.append(prompt)
        return model_result(typed_clean(prompt))

    verdict = await review_grounding(target, sources, deps, judge=judge)
    assert verdict.status == "supported"
    schema = prompts[0].split("\nDATA\n", 1)[0]
    enum = re.search(r'"kind"\s*:\s*(.*?)\s*,\s*"sources"', schema, re.S)
    assert enum is not None
    assert set(re.findall(r'"([^"]*)"', enum.group(1))) == KINDS


@pytest.mark.parametrize(
    "drift",
    ["artifact", "answer", "owner", "accepted_id", "root", "sources", "authority", "stable"],
)
async def test_judge_await_drift_invalidates_snapshot_without_extra_review(
    monkeypatch, tmp_path, drift
):
    import asyncio
    from dataclasses import replace

    from fusion_cli.core.evidence import CriterionEvidence
    from fusion_cli.core.execution_plan import VerificationCheckKind
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.research_grounding import finalize_grounding

    context, _, sources = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context = context
    deps.budget = loop._new_budget(deps.config)
    budget = deps.budget
    budget.research_required = True
    budget.research_contract = context.delivery_contract.accepted
    budget.research_sources.extend(sources)
    path = tmp_path / "report.html"
    path.write_text(GOOD)
    context.requested_outputs.add("report.html")
    outcome = AgentOutcome(f"Rapor: `{path}`.", [])
    mechanical = VerificationResult(
        True,
        evidence=(
            CriterionEvidence(
                "file_exists",
                VerificationCheckKind.FILE_EXISTS,
                EvidenceStatus.PASSED,
                "Report file exists",
                artifact=str(path),
            ),
        ),
    )
    calls = []

    async def judge(prompt, config, publisher):
        calls.append(prompt)
        await asyncio.sleep(0)
        if drift == "artifact":
            path.write_text(BAD)
        elif drift == "answer":
            outcome.final_text += " A newly added factual claim."
        elif drift == "owner":
            context.job_scope = "other-owner"
        elif drift == "accepted_id":
            context.delivery_contract.accepted = replace(
                context.delivery_contract.accepted, accepted_id="other-task"
            )
        elif drift == "root":
            context.root = tmp_path / "other-root"
            context.root.mkdir()
        elif drift == "sources":
            budget.research_sources.append(replace(sources[0], call_id="later-read"))
        elif drift == "authority":
            budget.research_contract = replace(budget.research_contract, accepted_id="revoked")
        return model_result(typed_clean(prompt))

    monkeypatch.setattr(loop.review, "_ask", judge)
    gate = await finalize_grounding(outcome, deps, mechanical)
    assert len(calls) == 1
    assert gate.evidence[0] == mechanical.evidence[0]
    assert str(path) in outcome.final_text
    if drift == "stable":
        assert gate.ok
        assert gate.evidence[-1].status is EvidenceStatus.PASSED
    else:
        assert not gate.ok
        assert gate.evidence[-1].status is EvidenceStatus.UNVERIFIED
        assert budget.research_verdict is None or budget.research_verdict.status != "supported"
    repeated = await finalize_grounding(outcome, deps, gate)
    assert repeated == gate
    assert len(calls) == 1
    assert budget.verify_rounds == 0


async def test_real_report_changed_during_judge_await_keeps_link_and_unverified_status(
    monkeypatch, tmp_path
):
    calls = []

    def judge(prompt):
        calls.append(prompt)
        (tmp_path / "report.html").write_text(BAD)
        return typed_clean(prompt)

    result, deps, _ = await run_report(monkeypatch, tmp_path, supported=True, typed_judge=judge)
    assert not result.ok
    assert len(calls) == 1
    assert "report.html" in result.final_text
    assert result.final_text.count("Olgusal kaynak denetimi tamamlanamadı.") == 1
    assert result.completion_report.gate.evidence[-1].status is EvidenceStatus.UNVERIFIED
    assert deps.require_budget().verify_rounds == 0


@pytest.mark.parametrize(
    "request_limit,external,hard,idle,expected",
    [
        (600, None, None, None, 600),
        (600, 90, 120, 100, 90),
        (600, 120, 70, 100, 70),
        (600, 120, 100, 65, 65),
        (45, 120, 100, 90, 45),
    ],
)
async def test_required_review_uses_existing_request_and_shared_remaining_time(
    monkeypatch, tmp_path, request_limit, external, hard, idle, expected
):
    from fusion_cli.core.turn_deadline import TurnDeadline
    from fusion_cli.engines.agent import research_grounding as grounding
    from tests.test_turn_deadline import FakeClock

    _, target, sources = target_sources(tmp_path)
    deps = _deps(
        tmp_path,
        RecordingSink(),
        runtime={
            "request_timeout_s": request_limit,
            "judge_timeout_s": 20,
            "judge_max_tokens": 3072,
            "max_tokens": 8192,
            "max_retries": 0,
        },
    )
    clock = FakeClock()
    deps.deadline = TurnDeadline.from_duration(external, clock)
    if hard is not None or idle is not None:
        deps.budget = loop._new_budget(deps.config, TurnDeadline.from_duration(hard or 120, clock))
        deps.budget.total_timeout_s = hard
        deps.budget.idle_timeout_s = idle
    original_config = deps.config
    requests = []
    waits = []

    class Provider:
        async def complete(self, request):
            requests.append(request)
            # Logical provider duration avoids waiting 56 real seconds offline.
            if expected > 56:
                clock.value += 56
            return model_result(typed_clean(request.messages[0].content))

    async def measured_wait(call, **kwargs):
        waits.append(kwargs["timeout"])
        return await call

    monkeypatch.setattr(grounding.review, "build_provider", lambda *args, **kwargs: Provider())
    monkeypatch.setattr(grounding.asyncio, "wait_for", measured_wait)
    result = await grounding.review_grounding(target, sources, deps)
    assert result.status == "supported"
    assert len(requests) == len(waits) == 1
    assert requests[0].timeout_s == waits[0] == expected
    assert requests[0].max_tokens == 8192
    assert requests[0].max_retries == 0
    assert deps.config is original_config
    assert deps.config.runtime.judge_timeout_s == 20
    assert deps.config.runtime.request_timeout_s == request_limit
    assert deps.config.runtime.max_tokens == 8192
    elapsed = 56 if expected > 56 else 0
    if deps.deadline is not None:
        assert deps.deadline.remaining_s() == external - elapsed
    if deps.budget is not None:
        assert deps.budget.remaining_s() == hard - elapsed
        assert deps.budget.idle_remaining_s() == idle - elapsed


@pytest.mark.parametrize("exhausted", ["external", "hard", "idle"])
async def test_exhausted_shared_review_time_is_unverified_without_judge_or_retry(
    monkeypatch, tmp_path, exhausted
):
    from fusion_cli.core.turn_deadline import TurnDeadline
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.research_grounding import finalize_grounding
    from tests.test_turn_deadline import FakeClock

    context, _, sources = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink(), runtime={"request_timeout_s": 600})
    deps.tool_context = context
    clock = FakeClock()
    deps.deadline = TurnDeadline.from_duration(1 if exhausted == "external" else 60, clock)
    budget = loop._new_budget(
        deps.config, TurnDeadline.from_duration(1 if exhausted == "hard" else 60, clock)
    )
    deps.budget = budget
    budget.idle_timeout_s = 1 if exhausted == "idle" else 60
    budget.research_required = True
    budget.research_contract = context.delivery_contract.accepted
    budget.research_sources.extend(sources)
    clock.value = 1
    calls = []

    async def judge(prompt, config, publisher):
        calls.append(prompt)
        return model_result(typed_clean(prompt))

    monkeypatch.setattr(loop.review, "_ask", judge)
    outcome = AgentOutcome("Orion release date from official sources.", [])
    first = await finalize_grounding(outcome, deps, VerificationResult(True))
    second = await finalize_grounding(outcome, deps, first)
    assert not calls
    assert first == second
    assert first.evidence[-1].status is EvidenceStatus.UNVERIFIED
    assert budget.verify_rounds == 0


async def test_required_review_timeout_cancels_transport_within_shared_hard_time(
    monkeypatch, tmp_path
):
    import asyncio

    from fusion_cli.core.clock import SystemClock
    from fusion_cli.core.turn_deadline import TurnDeadline
    from fusion_cli.engines.agent.research_grounding import review_grounding

    _, target, sources = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink(), runtime={"request_timeout_s": 600})
    deps.deadline = TurnDeadline.from_duration(0.03, SystemClock())
    calls = []
    cancelled = asyncio.Event()

    async def judge(prompt, config, publisher):
        calls.append(config.runtime.judge_timeout_s)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(loop.review, "_ask", judge)
    async with asyncio.timeout(0.3):
        verdict = await review_grounding(target, sources, deps)
    assert verdict.status == "incomplete"
    assert len(calls) == 1
    assert 0 < calls[0] <= 0.03
    assert cancelled.is_set()


async def test_external_cancellation_of_required_review_propagates(monkeypatch, tmp_path):
    import asyncio

    from fusion_cli.engines.agent.research_grounding import review_grounding

    _, target, sources = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink(), runtime={"request_timeout_s": 600})
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def judge(prompt, config, publisher):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(loop.review, "_ask", judge)
    task = asyncio.create_task(review_grounding(target, sources, deps))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


@pytest.mark.parametrize("normal_cap", [8192, 4096, 1024])
async def test_required_review_uses_configured_normal_output_cap_only(
    monkeypatch, tmp_path, normal_cap
):
    from fusion_cli.engines.agent import research_grounding as grounding

    _, target, sources = target_sources(tmp_path)
    deps = _deps(
        tmp_path,
        RecordingSink(),
        runtime={
            "request_timeout_s": 600,
            "judge_timeout_s": 20,
            "judge_max_tokens": 3072,
            "max_tokens": normal_cap,
            "max_retries": 0,
        },
    )
    original_config = deps.config
    requests = []

    class Provider:
        async def complete(self, request):
            requests.append(request)
            text = request.messages[0].content
            return model_result(typed_clean(text) if "\nDATA\n" in text else "TAMAM")

    monkeypatch.setattr(grounding.review, "build_provider", lambda *args, **kwargs: Provider())
    verdict = await grounding.review_grounding(target, sources, deps)
    optional = await grounding.review._ask("Optional generic review.", deps.config, deps.publisher)
    assert verdict.status == "supported" and optional.ok
    assert len(requests) == 2
    assert requests[0].max_tokens == normal_cap
    assert requests[0].timeout_s == 600
    assert requests[1].max_tokens == 3072
    assert requests[1].timeout_s == 20
    assert all(request.max_retries == 0 for request in requests)
    assert deps.config is original_config
    assert deps.config.runtime.max_tokens == normal_cap
    assert deps.config.runtime.judge_max_tokens == 3072
    assert deps.config.runtime.judge_timeout_s == 20


@pytest.mark.parametrize(
    "case,expected",
    [
        ("html_body_clipped", "truncated"),
        ("html_links_clipped", "truncated"),
        ("html_link_count_clipped", "truncated"),
        ("html_duplicate_after_cap", "complete"),
        ("html_nonhttp_after_cap", "complete"),
        ("html_complete", "complete"),
        ("html_short_links", "complete"),
        ("plain_complete", "complete"),
        ("plain_clipped", "truncated"),
        ("blocked", "blocked"),
    ],
)
def test_builtin_fetch_preserves_actual_html_rendering_truncation(
    monkeypatch, tmp_path, case, expected
):
    from fusion_cli.core.constants import MAX_OUTPUT_CHARS
    from fusion_cli.core.tools import ToolContext

    url = "https://orion.example/releases"
    content_type = "text/html"
    body = "<p>Orion 8 released October 25.</p>"
    if case == "html_body_clipped":
        body = (
            "<p>" + "Orion release notes. " * 5000 + "END_OF_DOCUMENT_FACT</p>"
            "<a href='/index'>Release index</a>"
        )
    elif case == "html_links_clipped":
        body = "<a href='/" + "x" * MAX_OUTPUT_CHARS + "__TAIL_TARGET__'>Release index</a>"
    elif case == "html_link_count_clipped":
        body = "".join(f"<a href='/release-{index}'>Release</a>" for index in range(80))
        body += "<a href='/discarded-extra'>Extra</a>"
    elif case in {"html_duplicate_after_cap", "html_nonhttp_after_cap"}:
        body = "".join(f"<a href='/release-{index}'>Release</a>" for index in range(80))
        extra = "/release-1" if case == "html_duplicate_after_cap" else "mailto:info@example.test"
        body += f"<a href='{extra}'>Extra</a>"
    elif case == "html_short_links":
        body += "<a href='/index'>Release index</a>"
    elif case.startswith("plain_"):
        content_type = "text/plain"
        body = "Orion 8 released October 25."
        if case == "plain_clipped":
            body *= MAX_OUTPUT_CHARS
    elif case == "blocked":
        body = "<p>Please enable javascript to continue</p>"
    assert len(body.encode()) < web.MAX_FETCH_BYTES
    monkeypatch.setattr(web, "url_block_reason", lambda value: None)
    monkeypatch.setattr(web, "fetch_following_redirects", lambda value: (content_type, body, url))
    result = web.web_fetch({"url": url}, ToolContext(root=tmp_path))
    assert result.source_receipt.completeness == expected
    assert result.source_receipt.text in result.output
    if case.startswith("html_"):
        rendered = web.page_text(body, url)
        assert isinstance(rendered, str)
        if expected == "truncated":
            assert len(rendered) < MAX_OUTPUT_CHARS
    if case == "html_body_clipped":
        assert "END_OF_DOCUMENT_FACT" not in result.source_receipt.text
    elif case == "html_links_clipped":
        assert "__TAIL_TARGET__" not in result.source_receipt.text
    elif case == "html_link_count_clipped":
        assert "/discarded-extra" not in result.source_receipt.text


@pytest.mark.parametrize("coverage", ["affected_only", "reviewed_all"])
def test_concrete_issue_can_fail_full_report_before_exhaustive_classification(tmp_path, coverage):
    import json

    from fusion_cli.engines.agent.research_grounding import (
        as_verification,
        parse_verdict,
        request_payload,
    )

    _, target, sources = target_sources(
        tmp_path,
        "Orion released October 26. " * 8 + "\n" + ("Report context. " * 20 + "\n") * 44,
    )
    assert len(target.spans) > 40
    payload = request_payload(target, sources)
    raw = json.loads(typed_issues("\nDATA\n" + json.dumps(payload)))
    first = target.spans[0].id
    raw["claims"][0]["targets"] = [first]
    raw["claims"][0]["basis"] = "The target gives October 26; read source s1:1 gives October 25."
    if coverage == "affected_only":
        raw["reviewed"] = [first]
    verdict = parse_verdict(json.dumps(raw), target, sources)
    assert verdict.status == "issues"
    gate = as_verification(verdict, target)
    assert not gate.ok
    assert gate.evidence[0].status is EvidenceStatus.FAILED
    assert first in gate.findings[0]


@pytest.mark.parametrize(
    "mutation",
    ["partial_supported", "empty_reviewed", "unreviewed_claim", "unknown_source", "no_issue"],
)
def test_early_issue_protocol_does_not_weaken_supported_or_bound_evidence(tmp_path, mutation):
    import json

    from fusion_cli.engines.agent.research_grounding import parse_verdict, request_payload

    _, target, sources = target_sources(tmp_path, ("Orion release context. " * 10 + "\n") * 4)
    payload = request_payload(target, sources)
    raw = json.loads(typed_issues("\nDATA\n" + json.dumps(payload)))
    first, second = target.spans[:2]
    raw["reviewed"] = [first.id]
    raw["claims"][0]["targets"] = [first.id]
    if mutation == "partial_supported":
        raw["status"] = "supported"
        raw["claims"][0]["kind"] = "supported"
    elif mutation == "empty_reviewed":
        raw["reviewed"] = []
    elif mutation == "unreviewed_claim":
        raw["claims"][0]["targets"] = [second.id]
    elif mutation == "unknown_source":
        raw["claims"][0]["sources"] = ["forged:1"]
    elif mutation == "no_issue":
        raw["claims"][0]["kind"] = "nonfactual"
    assert parse_verdict(json.dumps(raw), target, sources).status == "incomplete"

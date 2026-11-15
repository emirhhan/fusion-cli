"""V2 kökeni model metninden türetmez; V1 geçmiş sözleşmesi korunur."""

from __future__ import annotations

from fusion_cli.core.tool_emulation import parse_tool_calls, render_call


def test_v2_unknown_origin_warns_and_preserves_independent_read():
    text = render_call({"name": "read_file", "arguments": {"path": "a.py"}})
    parsed = parse_tool_calls(text, protocol="v2")
    assert [call.name for call in parsed.calls] == ["read_file"]
    assert any(
        warning.kind == "unverified_origin" and warning.blocks_mutation
        for warning in parsed.warnings
    )


def test_v2_unknown_fenced_reflection_never_becomes_call():
    text = (
        "```text\n"
        + render_call({"name": "write_file", "arguments": {"path": "a.py", "content": "x"}})
        + "\n```"
    )
    assert parse_tool_calls(text).calls
    parsed = parse_tool_calls(text, protocol="v2")
    assert parsed.calls == ()
    assert parsed.warnings


def observed_origin():
    from fusion_cli.core.web_provenance import WebCallContext, WebResponseProvenance

    context = WebCallContext("session-1", "turn-1", "attempt-1", "call-1")
    return WebResponseProvenance(
        transport_kind="browser",
        extraction_kind="dom_normalized_text",
        provider_id="fixture",
        observed_container_id="node-1",
        assistant_role_evidence="data-message-author-role=assistant",
        selector_id="[data-message-author-role]",
        selector_schema_version="1",
        selector_bundle_digest="a" * 64,
        adapter_revision="fusion-dom-v2",
        freshness_basis="new_node",
        origin_status="observed_assistant",
        content_kind="direct",
        call_context=context,
    )


def test_observed_current_assistant_fenced_call_is_parsed_without_authorizing_execution():
    origin = observed_origin()
    text = (
        "```\n"
        + render_call({"name": "write_file", "arguments": {"path": "a", "content": "b"}})
        + "\n```"
    )
    result = parse_tool_calls(
        text, protocol="v2", provenance=origin, call_context=origin.call_context
    )
    assert len(result.calls) == 1
    assert result.warnings == ()


def test_context_mismatch_and_quote_evidence_cannot_become_trusted():
    from dataclasses import replace

    origin = observed_origin()
    text = render_call({"name": "write_file", "arguments": {"path": "a", "content": "b"}})
    result = parse_tool_calls(text, protocol="v2", provenance=origin)
    assert any(warning.blocks_mutation for warning in result.warnings)
    quoted = replace(origin, content_kind="quoted")
    assert not parse_tool_calls(
        text, protocol="v2", provenance=quoted, call_context=quoted.call_context
    ).calls


def test_two_hundred_synthetic_negatives_have_no_parsed_calls():
    from pathlib import Path

    from fusion_cli.tools.emulation_eval import load_corpus, replay_corpus_report

    corpus = Path(__file__).parent / "fixtures/emulation/origin-v2.json"
    cases = load_corpus(corpus)
    assert len(cases) == 200
    for case in cases:
        parsed = parse_tool_calls(
            case.output,
            protocol=case.protocol,
            provenance=case.web_provenance,
            call_context=case.web_provenance.call_context if case.web_provenance else None,
        )
        assert parsed.calls == (), case.case_id
    report = replay_corpus_report(cases)
    assert report["recorded_cases"] == report["genuine_positive_cases"] == 0
    assert report["synthetic_negative_cases"] == 200


def test_snapshot_metadata_is_bound_to_same_observation_and_filters_secrets():
    from fusion_cli.providers.web_response import observed_response

    observed = observed_response(
        "aynı DOM metni",
        {
            "origin": {
                "role": "data-message-author-role=assistant",
                "container_id": "node-1",
                "message_id": "person@example.com",
                "quoted": False,
            }
        },
        provider_id="fixture",
        selector="[data-message-author-role]",
        selector_version="1",
        selector_digest="b" * 64,
    )
    assert observed.text == "aynı DOM metni"
    assert observed.provenance.observed_container_id == "node-1"
    assert observed.provenance.observed_message_id is None
    assert observed.provenance.origin_status == "observed_assistant"
    fallback = observed_response(
        "metin",
        "metin",
        provider_id="fixture",
        selector="article",
        selector_version="1",
        selector_digest="b" * 64,
    )
    assert fallback.provenance.origin_status == "unknown"


async def test_unknown_origin_warning_blocks_real_mutation_but_executes_independent_read(
    monkeypatch, tmp_path
):
    from fusion_cli.core.events import ToolExecuted
    from fusion_cli.core.types import ModelResult
    from fusion_cli.engines.agent import loop as agent_loop

    from .fakes import RecordingSink, ScriptedProvider, model_result, patch_providers
    from .test_agent_loop import _deps

    (tmp_path / "a.txt").write_text("başlangıç")
    text = (
        render_call({"name": "read_file", "arguments": {"path": "a.txt"}})
        + "\n"
        + render_call({"name": "write_file", "arguments": {"path": "b.txt", "content": "yetkisiz"}})
    )
    parsed = parse_tool_calls(text, protocol="v2")
    result = ModelResult(
        "fixture",
        "fixture",
        parsed.text,
        0,
        True,
        tool_calls=parsed.calls,
        parse_warnings=parsed.warnings,
    )
    provider = ScriptedProvider([result, model_result("Okunan dosya başlangıç içeriyor.")])
    patch_providers(
        monkeypatch, agent_loop, dict.fromkeys(("agent", "a", "b", "c", "hakem"), provider)
    )
    sink = RecordingSink()
    await agent_loop.run_agent(
        "Dosyayı oku.", _deps(tmp_path, sink), verify=False, self_review=False
    )
    assert not (tmp_path / "b.txt").exists()
    executed = [
        event
        for event in sink.events
        if isinstance(event, ToolExecuted) and event.outcome.value == "ok"
    ]
    assert [event.name for event in executed] == ["read_file"]


async def test_two_hundred_negatives_run_through_agent_without_executed_tools(
    monkeypatch, tmp_path
):
    from pathlib import Path

    from fusion_cli.core.events import ToolExecuted, ToolStarted
    from fusion_cli.core.types import ModelResult
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.tools.emulation_eval import load_corpus

    from .fakes import RecordingSink, ScriptedProvider, patch_providers
    from .test_agent_loop import _deps

    cases = load_corpus(Path(__file__).parent / "fixtures/emulation/origin-v2.json")
    sink = RecordingSink()
    for case in cases:
        parsed = parse_tool_calls(
            case.output,
            protocol="v2",
            provenance=case.web_provenance,
            call_context=case.web_provenance.call_context if case.web_provenance else None,
        )
        result = ModelResult(
            "fixture",
            "fixture",
            parsed.text,
            0,
            True,
            tool_calls=parsed.calls,
            parse_warnings=parsed.warnings,
        )
        provider = ScriptedProvider([result])
        patch_providers(
            monkeypatch, agent_loop, dict.fromkeys(("agent", "a", "b", "c", "hakem"), provider)
        )
        await agent_loop.run_agent(
            "Örneği açıkla.", _deps(tmp_path, sink), verify=False, self_review=False
        )
    assert len(cases) == 200
    assert not any(isinstance(event, (ToolStarted, ToolExecuted)) for event in sink.events)
    assert not list(tmp_path.glob("fixture-*"))


def test_reused_node_identity_cannot_gain_current_origin_from_increased_count():
    from fusion_cli.providers.web_response import ObservedResponse, accepted_snapshot

    origin = observed_origin()
    before = (ObservedResponse("eski", origin),)
    accepted = accepted_snapshot(
        ObservedResponse("yeni", origin), before, has_new_node=True, context=origin.call_context
    )
    assert accepted.provenance.freshness_basis == "unknown"
    assert not accepted.provenance.has_current_assistant_origin(origin.call_context)

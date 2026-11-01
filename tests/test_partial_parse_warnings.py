"""Kısmi protokol hatası sağlam okumayı ve kimlikleri kaybettirmez."""

from __future__ import annotations

import io
import json

from fusion_cli.core.events import (
    ModelCallFinished,
    ToolCallRepaired,
    ToolExecuted,
    ToolOutcome,
    ToolStarted,
)
from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.core.tool_emulation import CALL_CLOSE, CALL_OPEN, PAYLOAD_CLOSE, PAYLOAD_OPEN
from fusion_cli.core.types import CompletionRequest, Message
from fusion_cli.engines.agent.loop import run_agent
from fusion_cli.observability.json_sink import JsonRenderer
from fusion_cli.observability.replay import event_from_payload
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn

from .fakes import RecordingSink, ScriptedProvider, model_result, patch_providers
from .test_agent_loop import _deps, _kur


def _call(name: str, arguments: dict[str, object]) -> str:
    return f"{CALL_OPEN}\n{json.dumps({'name': name, 'arguments': arguments})}\n{CALL_CLOSE}"


async def _result(raw: str):
    async def transport(credential, messages, model):
        return WebTurn(raw)

    provider = WebProviderAdapter(
        model="test",
        credential=WebSessionCredential(),
        transport=transport,
        tool_support=ToolSupport.EMULATED,
    )
    return await provider.complete(
        CompletionRequest(
            messages=(Message("user", "oku"),), temperature=0, max_tokens=1000, timeout_s=1
        )
    )


async def test_partial_warning_survives_web_agent_jsonl_without_repeating_read(
    monkeypatch, tmp_path
):
    (tmp_path / "a.txt").write_text("başlangıç", encoding="utf-8")
    raw = (
        _call("read_file", {"path": "a.txt"})
        + "\n"
        + _call("write_file", {"path": "b.txt", "content": "belirsiz"})
        + f"\n{CALL_OPEN}\n{{bozuk\n{CALL_CLOSE}"
    )
    result = await _result(raw)
    assert result.parse_warnings, "Sağlam çağrının yanındaki hata kayboldu"
    assert result.parse_warnings[0].call_index == 2
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    deps.conversation_id = "conversation-1"
    provider = ScriptedProvider([result, model_result("Okunan dosya başlangıç içeriyor.")])
    from fusion_cli.engines.agent import loop as agent_loop

    patch_providers(
        monkeypatch, agent_loop, dict.fromkeys(("agent", "a", "b", "c", "hakem"), provider)
    )
    outcome = await run_agent("Dosyayı oku.", deps, verify=False, self_review=False)
    executed = [event for event in sink.events if isinstance(event, ToolExecuted)]
    assert [event.name for event in executed if event.outcome.value == "ok"] == ["read_file"]
    assert not (tmp_path / "b.txt").exists()
    assert any(
        message.harness_note
        and "yalnız" in message.content.lower()
        and "tekrar" in message.content.lower()
        for message in outcome.messages
    )
    started = [event for event in sink.events if isinstance(event, ToolStarted)]
    assert [event.call_id for event in started] == [result.tool_calls[0].id]
    assert {event.call_id for event in executed} == {call.id for call in result.tool_calls}
    repairs = [event for event in sink.events if isinstance(event, ToolCallRepaired)]
    assert repairs and repairs[0].call_id is None
    stream = io.StringIO()
    for event in sink.events:
        JsonRenderer(stream).handle(event)
    restored = [event_from_payload(json.loads(line)) for line in stream.getvalue().splitlines()]
    recorded = next(
        event.result
        for event in restored
        if isinstance(event, ModelCallFinished) and event.result.parse_warnings
    )
    assert recorded.parse_warnings == result.parse_warnings
    assert recorded.tool_calls == result.tool_calls
    correlated = [
        event
        for event in restored
        if isinstance(event, (ToolStarted, ToolExecuted, ModelCallFinished, ToolCallRepaired))
    ]
    assert {event.session_id for event in correlated} == {"conversation-1"}
    assert len({event.turn_id for event in correlated}) == 1
    assert all(event.turn_id for event in correlated)


async def test_unused_payload_warning_does_not_block_known_mutation(monkeypatch, tmp_path):
    raw = (
        _call("write_file", {"path": "created.txt", "content": "tam"})
        + f'\n{PAYLOAD_OPEN} id="unused"\nartık\n{PAYLOAD_CLOSE}'
    )
    result = await _result(raw)
    assert result.parse_warnings and not result.parse_warnings[0].blocks_mutation
    sink = RecordingSink()
    _kur(monkeypatch, ScriptedProvider([result, model_result("Dosya hazır.")]))
    await run_agent(
        "created.txt dosyasını oluştur.", _deps(tmp_path, sink), verify=False, self_review=False
    )
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "tam"


async def test_two_reads_keep_independent_call_ids(monkeypatch, tmp_path):
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    result = await _result(
        _call("read_file", {"path": "a.txt"}) + "\n" + _call("read_file", {"path": "b.txt"})
    )
    sink = RecordingSink()
    _kur(monkeypatch, ScriptedProvider([result, model_result("İki dosya okundu.")]))
    await run_agent("İki dosyayı oku.", _deps(tmp_path, sink), verify=False, self_review=False)
    started = [event for event in sink.events if isinstance(event, ToolStarted)]
    finished = [event for event in sink.events if isinstance(event, ToolExecuted)]
    assert [event.call_id for event in started] == [call.id for call in result.tool_calls]
    assert [event.call_id for event in finished] == [call.id for call in result.tool_calls]


async def test_valid_read_and_broken_write_only_repairs_missing_step(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("ok", encoding="utf-8")
    result = await _result(
        _call("read_file", {"path": "a.txt"})
        + f'\n{CALL_OPEN}\n{{"name":"write_file","arguments":"bozuk"}}\n{CALL_CLOSE}'
    )
    assert result.parse_warnings[0].call_index == 1
    sink = RecordingSink()
    _kur(monkeypatch, ScriptedProvider([result, model_result("Dosya okundu.")]))
    outcome = await run_agent("a.txt oku.", _deps(tmp_path, sink), verify=False, self_review=False)
    assert [event.name for event in sink.events if isinstance(event, ToolStarted)] == ["read_file"]
    assert any(
        message.harness_note and "eksik adımı" in message.content for message in outcome.messages
    )


async def test_successful_mutation_is_not_executed_again_after_warning(monkeypatch, tmp_path):
    raw = _call("write_file", {"path": "created.txt", "content": "tam"})
    result = await _result(raw + f'\n{PAYLOAD_OPEN} id="unused"\nartık\n{PAYLOAD_CLOSE}')
    repeated = await _result(raw)
    sink = RecordingSink()
    _kur(monkeypatch, ScriptedProvider([result, repeated, model_result("Dosya hazır.")]))
    await run_agent("created.txt oluştur.", _deps(tmp_path, sink), verify=False, self_review=False)
    assert [event.name for event in sink.events if isinstance(event, ToolStarted)] == ["write_file"]
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "tam"


async def test_cli_receipt_attempt_reaches_tool_events_and_legacy_caller(monkeypatch, tmp_path):
    from dataclasses import replace

    from fusion_cli.appserver.bridges import ProtocolSink
    from fusion_cli.cli import session
    from fusion_cli.core.submission import SubmissionKey, SubmissionReceipt, SubmissionState
    from fusion_cli.engines.agent.loop import AgentOutcome

    from .fakes import make_config

    receipt = SubmissionReceipt(
        SubmissionKey("profile", str(tmp_path), "conv-receipt", "request"),
        "receipt:1",
        SubmissionState.RUNNING,
    )
    emitted = []
    protocol_sink = ProtocolSink(emitted.append, receipt=receipt, sequence=iter(range(41, 100)))
    sink = RecordingSink()
    jsonl = io.StringIO()

    async def fake_runner(task, deps, **kwargs):
        deps.publisher.publish(ToolStarted(name="read_file", args={}, call_id="actual-call"))
        deps.publisher.publish(
            ToolExecuted(
                name="read_file",
                args={},
                call_id="actual-call",
                outcome=ToolOutcome.OK,
                output="ok",
            )
        )
        deps.publisher.publish(ToolStarted(name="read_file", args={}, call_id="second-call"))
        return AgentOutcome("bitti", [], ok=True)

    monkeypatch.setattr(session, "run_agent", fake_runner)
    from fusion_cli.core.events import StatusChanged

    monkeypatch.setattr(
        session,
        "_warn_if_unavailable",
        lambda store, bus: bus.publish(StatusChanged("kuyrukta ilk")),
    )
    config = replace(make_config(), mcp_servers=())
    await session.run_agent_task(
        "oku",
        config,
        sinks=(protocol_sink, sink, JsonRenderer(jsonl)),
        prompter_factory=lambda _drain: None,
        root=tmp_path,
        interactive=False,
        conversation_id=receipt.key.conversation_id,
        attempt_id=receipt.attempt_id,
        event_correlator=protocol_sink.correlate,
    )
    event = next(event for event in sink.events if isinstance(event, ToolStarted))
    assert event.turn_id == event.attempt_id == receipt.attempt_id
    assert event.session_id == receipt.key.conversation_id
    wire = next(json.loads(line) for line in emitted if "actual-call" in line)
    assert receipt.attempt_id in json.dumps(wire)
    wire_events = [json.loads(line)["veri"] for line in emitted]
    json_events = [json.loads(line) for line in jsonl.getvalue().splitlines()]
    keys = ("event_id", "session_id", "turn_id", "attempt_id")
    assert len(wire_events) == len(json_events) == len(sink.events)
    for wire_event, json_event, recorded in zip(wire_events, json_events, sink.events, strict=True):
        assert {key: wire_event.get(key) for key in keys} == {
            key: json_event.get(key) for key in keys
        }
        assert {key: wire_event.get(key) for key in keys} == {
            key: getattr(recorded, key, None) for key in keys
        }
    assert [event["event_id"] for event in wire_events] == [
        f"{receipt.attempt_id}:{index}" for index in range(41, 41 + len(wire_events))
    ]
    legacy = RecordingSink()
    await session.run_agent_task(
        "oku",
        config,
        sinks=(legacy,),
        prompter_factory=lambda _drain: None,
        root=tmp_path,
        interactive=False,
    )
    event = next(event for event in legacy.events if isinstance(event, ToolStarted))
    assert event.attempt_id and event.turn_id == event.attempt_id


async def test_warning_jsonl_replay_retains_identity_and_warning():
    from fusion_cli.providers.replay import ReplayProvider, recorded_results

    result = await _result(
        _call("read_file", {"path": "a"}) + f"\n{CALL_OPEN}\n{{bozuk\n{CALL_CLOSE}"
    )
    stream = io.StringIO()
    JsonRenderer(stream).handle(
        ModelCallFinished(
            role="agent",
            result=result,
            call_id="model-id",
            event_id="event-id",
            session_id="session-id",
            turn_id="attempt-id",
        )
    )
    event = event_from_payload(json.loads(stream.getvalue()))
    assert isinstance(event, ModelCallFinished)
    provider = ReplayProvider(recorded_results([event]))
    restored = await provider.complete(
        CompletionRequest(messages=(), temperature=0, max_tokens=10, timeout_s=1)
    )
    assert restored == result
    assert restored.tool_calls[0].id != event.call_id
    assert (event.event_id, event.session_id, event.turn_id) == (
        "event-id",
        "session-id",
        "attempt-id",
    )


def test_scope_uses_injected_ids_and_preserves_existing_correlation():
    from fusion_cli.core.event_scope import TurnPublisher

    sink = RecordingSink()

    class Publisher:
        def publish(self, event):
            sink.handle(event)

    ids = iter(("injected-attempt", "injected-event", "second-event"))
    scoped = TurnPublisher(Publisher(), session_id="conversation", id_factory=lambda: next(ids))
    scoped.publish(ToolStarted(name="read_file", args={}, call_id="actual-call"))
    first = sink.events[0]
    assert (first.turn_id, first.attempt_id, first.event_id) == (
        "injected-attempt",
        "injected-attempt",
        "injected-event",
    )
    original = ToolExecuted(
        name="read_file",
        args={},
        output="ok",
        outcome=ToolOutcome.OK,
        call_id="existing-call",
        attempt_id="receipt-attempt",
        event_id="existing-event",
        turn_id="receipt-attempt",
        session_id="receipt-conversation",
        schema_version=1,
    )
    scoped.publish(original)
    assert sink.events[1] == original


def test_receipt_sink_stamps_legacy_special_event_once_and_keeps_receiptless_shape():
    from fusion_cli.appserver.bridges import ProtocolSink
    from fusion_cli.core.events import FusionCompleted
    from fusion_cli.core.submission import SubmissionKey, SubmissionReceipt, SubmissionState
    from fusion_cli.core.types import FusionResult, VerdictSource

    receipt = SubmissionReceipt(
        SubmissionKey("p", "root", "c", "r"), "attempt:1", SubmissionState.RUNNING
    )
    lines = []
    sink = ProtocolSink(lines.append, receipt=receipt, sequence=iter((7, 8)))
    special = FusionCompleted(
        FusionResult("soru", "bilgi", "model", "yanıt", VerdictSource.SINGLE, ())
    )
    correlated = sink.correlate(special)
    sink.handle(correlated)
    sink.handle(ToolStarted(name="read_file", args={}))
    first, second = [json.loads(line)["veri"] for line in lines]
    assert first["event_id"] == "attempt:1:7"
    assert first["session_id"] == "c" and first["turn_id"] == "attempt:1"
    assert second["event_id"] == "attempt:1:8" and second["attempt_id"] == "attempt:1"
    legacy = []
    ProtocolSink(legacy.append).handle(ToolStarted(name="read_file", args={}))
    payload = json.loads(legacy[0])["veri"]
    assert "event_id" not in payload and "session_id" not in payload and "turn_id" not in payload

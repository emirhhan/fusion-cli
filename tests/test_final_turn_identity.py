"""Gerçek CLI sınırında tek tur kimliği, özgün iz ve köken bağlamı."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fusion_cli.cli.session import run_agent_task
from fusion_cli.core.events import ToolExecuted
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    RetrySafety,
    RoutineDefinition,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.context_projection import OriginalCursor
from fusion_cli.engines.agent.routine_observer import begin_routine
from fusion_cli.memory.turn_journal import FileTurnJournal

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


class _Provider(ScriptedProvider):
    def __init__(self):
        super().__init__(
            [
                model_result(tool_calls=[tool_call("read_file", path="girdi.txt")]),
                model_result("Dosya okundu."),
            ]
        )
        self.requests = []

    def _next(self, request):
        self.requests.append(request)
        return super()._next(request)


def _routine():
    checks = (
        VerificationCheck("once", VerificationCheckKind.FILE_EXISTS, "girdi.txt"),
        VerificationCheck("sonra", VerificationCheckKind.FILE_CONTAINS, "sonuc.txt", "tamam"),
    )
    return ExecutionPlan(
        "rutin",
        "dosyayı üret",
        (
            PlanStep(
                "adim",
                "sonuc.txt yaz",
                (),
                (),
                ("files",),
                ("once", "sonra"),
                "",
                RetrySafety.SAFE,
                verification_checks=checks,
            ),
        ),
        routine=RoutineDefinition('{"type":"object"}', ("once",), ("sonra",)),
    )


async def _run(tmp_path, monkeypatch, attempt_id):
    (tmp_path / "girdi.txt").write_text("hazır")
    config = make_config(
        memory_dir=tmp_path / "bellek",
        mcp_servers=(),
        runtime={
            "context_original_trace": True,
            "emulation_protocol": "v2",
            "verified_skill_proposals": True,
        },
    )
    provider, sink, captured = _Provider(), RecordingSink(), {}
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    journal = FileTurnJournal(tmp_path / "turn.json", original_owner_id="session")
    old_call = replace(tool_call("read_file", path="eski.txt"), id="previous-call")
    history = [
        Message("assistant", "", tool_calls=(old_call,)),
        Message("tool", "ESKI-TUR", tool_call_id=old_call.id),
    ]

    async def actual_runner(task, deps, **kwargs):
        captured["deps"] = deps
        captured["boundary_id"] = deps.attempt_id
        captured["publisher"] = deps.publisher
        deps.original_cursor = OriginalCursor(turn_id="bayat")
        result = await loop.run_agent(task, deps, **kwargs)
        captured["routine"] = await begin_routine(_routine(), deps)
        return result

    outcome = await run_agent_task(
        "girdi.txt dosyasını oku",
        config,
        sinks=(sink,),
        prompter_factory=lambda _drain: AlwaysApprove(),
        root=tmp_path,
        interactive=False,
        journal=journal,
        history=history,
        attempt_id=attempt_id,
        conversation_id="session",
        turn_runner=actual_runner,
    )
    assert outcome.ok and outcome.tool_calls_made == 1
    return captured, provider, sink, journal, old_call.id


@pytest.mark.parametrize("attempt_id", [None, "receipt-attempt"])
async def test_cli_ve_receipt_ayni_kimligi_motor_olay_ve_ozgun_ize_tasir(
    tmp_path, monkeypatch, attempt_id
):
    captured, provider, sink, journal, old_id = await _run(tmp_path, monkeypatch, attempt_id)
    deps = captured["deps"]
    identity = captured["boundary_id"]
    assert identity and (attempt_id is None or identity == attempt_id)
    assert deps.attempt_id == identity
    assert deps.publisher is captured["publisher"]
    assert deps.original_cursor.turn_id == identity
    assert deps.original_cursor.excluded_call_ids == frozenset((old_id,))
    events = [event for event in sink.events if isinstance(event, ToolExecuted)]
    assert len(events) == 1 and events[0].turn_id == events[0].attempt_id == identity
    records = [json.loads(line) for line in journal.original_path.read_text().splitlines()]
    assert records and {record["tur"] for record in records} == {identity}
    assert "ESKI-TUR" not in journal.original_path.read_text()
    contexts = [request.web_call_context for request in provider.requests]
    assert all(
        context and context.turn_id == context.attempt_id == identity for context in contexts
    )
    assert all(context.session_id == "session" for context in contexts)
    assert all(request.emulation_protocol == "v2" for request in provider.requests)
    assert captured["routine"] is not None


async def test_appserver_receipt_kimligi_gercek_motor_ve_gunlukte_korunur(tmp_path, monkeypatch):
    from fusion_cli.appserver.session import AppSession
    from fusion_cli.core.submission import SubmissionKey, SubmissionReceipt, SubmissionState

    (tmp_path / "girdi.txt").write_text("hazır")
    config = make_config(
        memory_dir=tmp_path / "memory",
        mcp_servers=(),
        runtime={
            "context_original_trace": True,
            "emulation_protocol": "v2",
        },
    )
    monkeypatch.setattr("fusion_cli.appserver.session.load_config", lambda: config)
    provider, captured = _Provider(), {}
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)

    async def actual_runner(task, deps, **kwargs):
        captured["identity"] = deps.attempt_id
        result = await loop.run_agent(task, deps, **kwargs)
        captured["cursor"] = deps.original_cursor.turn_id
        captured["records"] = [
            json.loads(line) for line in deps.journal.original_path.read_text().splitlines()
        ]
        return result

    monkeypatch.setattr("fusion_cli.cli.session.run_agent", actual_runner)
    lines = []
    app = AppSession(lines.append, root=tmp_path, home=tmp_path / "ev")
    receipt = SubmissionReceipt(
        SubmissionKey("offline", str(tmp_path), "app", "request"),
        "request:1",
        SubmissionState.RUNNING,
    )
    try:
        result = await app._run_turn("girdi.txt dosyasını oku", receipt=receipt)
        assert result["ok"]
        assert captured["identity"] == captured["cursor"] == receipt.attempt_id
        assert {record["tur"] for record in captured["records"]} == {receipt.attempt_id}
        assert all(
            request.web_call_context.attempt_id == receipt.attempt_id
            for request in provider.requests
        )
    finally:
        await app.close()


async def test_onceden_sarilmis_yayincinin_varolan_kimligi_motor_icin_kullanilir(
    tmp_path, monkeypatch
):
    from fusion_cli.core.event_scope import TurnPublisher

    from .test_agent_loop import _deps

    (tmp_path / "girdi.txt").write_text("hazır")
    sink, provider = RecordingSink(), _Provider()
    deps = _deps(tmp_path, sink, runtime={"context_original_trace": True})
    deps.conversation_id = "session"
    deps.publisher = TurnPublisher(deps.publisher, session_id="session", attempt_id="varolan")
    deps.journal = FileTurnJournal(tmp_path / "journal.json", original_owner_id="session")
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)

    def forbidden_identity():
        raise AssertionError("Mevcut yayıncı için ikinci tur kimliği üretilmemeli")

    deps.trace_id_factory = forbidden_identity
    result = await loop.run_agent("girdi.txt dosyasını oku", deps)
    assert result.ok
    assert deps.original_cursor.turn_id == "varolan"
    assert deps.journal.original_path.exists()
    assert all(request.web_call_context.attempt_id == "varolan" for request in provider.requests)
    assert {event.turn_id for event in sink.events if isinstance(event, ToolExecuted)} == {
        "varolan"
    }
    assert deps.attempt_id is None

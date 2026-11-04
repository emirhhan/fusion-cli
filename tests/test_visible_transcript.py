"""Public tool history survives desktop close without entering model context."""

from __future__ import annotations

from fusion_cli.appserver.protocol import Request
from fusion_cli.cli.repl.transcript_store import load_transcript_messages
from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.loop import AgentOutcome
from tests.test_appserver_session import _session, _sonuc


async def test_completed_tool_turn_survives_close_reload_without_model_context(
    tmp_path, monkeypatch
):
    secret = "sk-or-v1-" + "x" * 48
    diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new"
    command = "echo " + "x" * 5000 + " api_key=" + secret

    async def run(task, _config, **kwargs):
        sink = kwargs["sinks"][0]
        sink.handle(
            ToolExecuted(
                name="edit_file",
                args={"path": "a.py"},
                outcome=ToolOutcome.OK,
                output="saved",
                diff=diff,
                call_id="write",
            )
        )
        sink.handle(
            ToolExecuted(
                name="run_shell",
                args={"command": command, "api_key": secret},
                outcome=ToolOutcome.FAILED,
                output="failure " + "z" * 5000 + "\n" + secret,
                diff="must not show",
                call_id="shell",
            )
        )
        return AgentOutcome(
            ok=True,
            final_text="Done",
            messages=[
                *kwargs["history"],
                Message("user", task),
                Message("tool", "RAW_MODEL_TOOL_SENTINEL", name="run_shell", ok=False),
                Message("assistant", "Done"),
            ],
        )

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    lines = []
    session = _session(tmp_path, lines)
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "tools"}))
    await session.handle(Request("run", "tur.calistir", {"gorev": "inspect and save"}))
    assert _sonuc(lines, "run")["ok"] is True
    memory = session._state.config.memory_dir
    await session.close()

    reopened_lines = []
    reopened = _session(tmp_path, reopened_lines)
    await reopened.handle(Request("start", "oturum.baslat", {"sohbet_id": "tools"}))
    await reopened.handle(Request("history", "oturum.gecmis", {}))
    rows = _sonuc(reopened_lines, "history")["mesajlar"]
    assert [row["rol"] for row in rows] == ["kullanici", "olay", "olay", "asistan"]
    events = [row["olay"] for row in rows if row["rol"] == "olay"]
    assert events[0]["diff"] == diff
    assert events[1]["outcome"] == "failed"
    assert events[1]["diff"] is None
    assert len(events[1]["output"]) <= 4000 and events[1]["output"].endswith("…")
    assert len(events[1]["args"]["command"]) <= 4000
    assert events[1]["history_truncated"]
    assert secret not in str(rows)
    assert "RAW_MODEL_TOOL_SENTINEL" not in str(rows)
    model = load_transcript_messages(memory, tmp_path, conversation_id="tools")
    assert [message.role for message in model] == ["user", "assistant"]
    assert "failure" not in str(model) and command not in str(model)
    await reopened.close()


def _public_event(**extra):
    return {
        "olay": "ToolExecuted",
        "name": "run_shell",
        "args": {"command": "echo safe"},
        "outcome": "ok",
        "output": "public result",
        **extra,
    }


def test_recorder_filters_identity_private_events_and_replays(tmp_path):
    import json

    from fusion_cli.appserver.protocol import encode_event
    from fusion_cli.appserver.visible_transcript import VisibleToolRecorder, load_visible_transcript
    from fusion_cli.cli.repl.transcript_store import TranscriptStore

    store = TranscriptStore(tmp_path / "memory", tmp_path, conversation_id="a")
    active = True
    recorder = VisibleToolRecorder(store, active=lambda: active, turn_id="attempt-a")
    event = _public_event(
        event_id="attempt-a:1", turn_id="attempt-a", session_id="a", call_id="same"
    )
    recorder.record(encode_event(event))
    recorder.record(encode_event(event))
    recorder.record(encode_event(_public_event(event_id="attempt-a:2", turn_id="wrong")))
    recorder.record(encode_event(_public_event(session_id="another", turn_id="attempt-a")))
    recorder.record(encode_event({"olay": "ModelToken", "text": "PRIVATE_TOKEN"}))
    recorder.record(encode_event(_public_event(agent_id="child", turn_id="attempt-a")))
    recorder.record("{broken")
    active = False
    recorder.record(encode_event(_public_event(turn_id="attempt-a")))
    next_attempt = VisibleToolRecorder(store, active=lambda: True, turn_id="attempt-b")
    next_attempt.record(
        encode_event(_public_event(event_id="attempt-b:1", turn_id="attempt-b", call_id="same"))
    )
    history = load_visible_transcript(store, [])
    assert len(history.rows) == 2
    assert [row["id"] for row in history.rows] == ["attempt-a:1", "attempt-b:1"]
    assert "PRIVATE_TOKEN" not in store.events_path.read_text()
    records = [json.loads(line) for line in store.events_path.read_text().splitlines()]
    assert all(record["event"] == "VisibleToolExecuted" for record in records)


def test_public_projection_redacts_before_clipping_and_drops_unknown_private_args(tmp_path):
    from fusion_cli.appserver.visible_transcript import load_visible_transcript, public_tool_payload
    from fusion_cli.cli.repl.transcript_store import TranscriptStore

    secret = "sk-or-v1-" + "a" * 48
    raw = _public_event(
        args={
            "command": "echo api_key=" + secret + "\n" + "é" * 5000,
            "private_blob": "DO_NOT_PERSIST",
            "x": 10**500,
        },
        output=secret + "\n" + "o" * 5000,
        diff="d" * 5000,
    )
    payload = public_tool_payload(raw, session_id="a")
    assert payload is not None
    assert secret not in str(payload) and "DO_NOT_PERSIST" not in str(payload)
    assert payload["history_truncated"] == ["args.command", "output", "diff"]
    assert "x" not in payload["args"]
    store = TranscriptStore(tmp_path / "memory", tmp_path, conversation_id="a")
    store.record_visible_tool(payload, identifier="one")
    restored = load_visible_transcript(store, [])
    assert len(restored.rows) == 1
    assert len(restored.rows[0]["olay"]["diff"]) <= 4000
    assert secret not in store.events_path.read_text()


def test_ui_history_fails_closed_on_corruption_scope_and_legacy_raw_tools(tmp_path):
    import json

    from fusion_cli.appserver.visible_transcript import load_visible_transcript
    from fusion_cli.cli.repl.transcript_store import TranscriptStore, delete_conversation

    store = TranscriptStore(tmp_path / "memory", tmp_path, conversation_id="a")
    store.record_user("task")
    store.record_visible_tool(_public_event(), identifier="valid")
    with store.events_path.open("a") as stream:
        stream.write("{broken\n")
        for record in [
            {"event": "ToolExecuted", "name": "PRIVATE_LEGACY", "output": "PRIVATE_LEGACY"},
            {"event": "VisibleToolExecuted", "visible_version": 99, "payload": _public_event()},
            {
                "event": "VisibleToolExecuted",
                "visible_version": 1,
                "visible_id": "bad",
                "payload": _public_event(outcome="bogus"),
            },
            {
                "event": "VisibleToolExecuted",
                "visible_version": 1,
                "visible_id": "other",
                "payload": _public_event(session_id="other"),
            },
        ]:
            stream.write(json.dumps({"session_id": "a", **record}) + "\n")
    other = TranscriptStore(tmp_path / "memory", tmp_path, conversation_id="b")
    other.record_visible_tool(_public_event(), identifier="sibling")
    rows = load_visible_transcript(store, []).rows
    assert [row.get("id") for row in rows if row["rol"] == "olay"] == ["valid"]
    assert "PRIVATE_LEGACY" not in str(rows)
    delete_conversation(tmp_path / "memory", tmp_path, "a")
    assert load_visible_transcript(store, [Message("user", "fallback")]).rows == []


def test_ui_history_clear_rewind_and_limits_are_bounded_and_explicit(tmp_path, monkeypatch):
    from fusion_cli.appserver import visible_transcript as module
    from fusion_cli.appserver.protocol import encode_event
    from fusion_cli.cli.repl.transcript_store import TranscriptStore

    monkeypatch.setattr(module, "MAX_ROWS", 3)
    store = TranscriptStore(tmp_path / "memory", tmp_path, conversation_id="a")
    recorder = module.VisibleToolRecorder(store, active=lambda: True)
    for i in range(8):
        recorder.record(encode_event(_public_event(event_id=f"event-{i}")))
    history = module.load_visible_transcript(store, [])
    assert len(history.rows) == 3 and history.truncated
    assert store.events_path.read_text().count('"event": "VisibleToolExecuted"') == 3
    store.record_visible_clear()
    store.record_user("keep")
    store.record_visible_tool(_public_event(), identifier="keep")
    store.record_user("remove")
    store.record_visible_tool(_public_event(), identifier="remove")
    store.record_rewind(1)
    history = module.load_visible_transcript(store, [])
    assert not any(row.get("id") == "remove" for row in history.rows)
    assert [row["rol"] for row in history.rows] == ["olay"]
    assert history.rows[0]["id"] == "keep"


async def test_close_preserves_completed_partial_tools_and_fences_late_events(
    tmp_path, monkeypatch
):
    import asyncio

    started = asyncio.Event()
    sink_holder = []

    async def run(_task, _config, **kwargs):
        sink = kwargs["sinks"][0]
        sink_holder.append(sink)
        sink.handle(
            ToolExecuted(
                name="read_file",
                args={"path": "public.txt"},
                outcome=ToolOutcome.OK,
                output="already completed",
                call_id="partial",
            )
        )
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    lines = []
    session = _session(tmp_path, lines)
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "partial"}))
    pending = asyncio.create_task(
        session.handle(Request("run", "tur.calistir", {"gorev": "read files"}))
    )
    await started.wait()
    await session.close()
    await pending
    sink_holder[0].handle(
        ToolExecuted(name="late_tool", args={}, outcome=ToolOutcome.OK, output="must not persist")
    )
    reopened_lines = []
    reopened = _session(tmp_path, reopened_lines)
    await reopened.handle(Request("start", "oturum.baslat", {"sohbet_id": "partial"}))
    await reopened.handle(Request("history", "oturum.gecmis", {}))
    rows = _sonuc(reopened_lines, "history")["mesajlar"]
    tools = [row["olay"] for row in rows if row["rol"] == "olay"]
    assert [event["name"] for event in tools] == ["read_file"]
    assert tools[0]["output"] == "already completed"
    assert "must not persist" not in reopened._transcript_store.events_path.read_text()
    await reopened.close()


async def test_session_clear_and_switch_do_not_replay_previous_tool_rows(tmp_path, monkeypatch):
    sinks = []

    async def run(task, _config, **kwargs):
        sink = kwargs["sinks"][0]
        sinks.append(sink)
        sink.handle(
            ToolExecuted(name="read_file", args={"path": task}, outcome=ToolOutcome.OK, output=task)
        )
        return AgentOutcome(
            ok=True,
            final_text="done",
            messages=[*kwargs["history"], Message("user", task), Message("assistant", "done")],
        )

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    lines = []
    session = _session(tmp_path, lines)
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "a"}))
    await session.handle(Request("run1", "tur.calistir", {"gorev": "old"}))
    await session.handle(Request("clear", "komut.calistir", {"ad": "clear"}))
    await session.handle(Request("history1", "oturum.gecmis", {}))
    assert _sonuc(lines, "history1")["mesajlar"] == []
    await session.handle(Request("run2", "tur.calistir", {"gorev": "new"}))
    sinks[0].handle(ToolExecuted(name="late_tool", args={}, outcome=ToolOutcome.OK, output="late"))
    await session.handle(Request("history2", "oturum.gecmis", {}))
    rows = _sonuc(lines, "history2")["mesajlar"]
    assert [row["olay"]["output"] for row in rows if row["rol"] == "olay"] == ["new"]
    await session.handle(Request("switch", "oturum.baslat", {"sohbet_id": "b"}))
    await session.handle(Request("history3", "oturum.gecmis", {}))
    assert _sonuc(lines, "history3")["mesajlar"] == []
    await session.close()


def test_bounded_tail_and_project_scope_never_reconstruct_missing_tools(tmp_path, monkeypatch):
    from fusion_cli.appserver import visible_transcript as module
    from fusion_cli.cli.repl.transcript_store import TranscriptStore

    root = tmp_path / "project"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    memory = tmp_path / "memory"
    store = TranscriptStore(memory, root, conversation_id="same-id")
    store.record_user("old text " * 1000)
    store.record_visible_tool(_public_event(), identifier="latest")
    wrong = TranscriptStore(memory, other, conversation_id="same-id")
    wrong.record_visible_tool(_public_event(output="other-project"), identifier="wrong")
    monkeypatch.setattr(module, "MAX_READ_BYTES", 600)
    history = module.load_visible_transcript(store, [])
    assert history.truncated
    assert [row["id"] for row in history.rows] == ["latest"]
    assert "other-project" not in str(history.rows)


async def test_history_reply_fenced_when_conversation_changes_during_read(tmp_path, monkeypatch):
    import asyncio
    import threading

    from fusion_cli.appserver import session as module

    entered, release = threading.Event(), threading.Event()
    loader = module.load_visible_transcript

    def blocked(store, fallback):
        entered.set()
        assert release.wait(5)
        return loader(store, fallback)

    monkeypatch.setattr(module, "load_visible_transcript", blocked)
    lines = []
    session = _session(tmp_path, lines)
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "a"}))
    request = asyncio.create_task(session.handle(Request("history", "oturum.gecmis", {})))
    assert await asyncio.to_thread(entered.wait, 5)
    await session.handle(Request("switch", "oturum.baslat", {"sohbet_id": "b"}))
    release.set()
    await request
    assert _sonuc(lines, "history")["ok"] is False
    await session.close()


async def test_import_replaces_existing_tool_view_instead_of_replaying_old_work(
    tmp_path, monkeypatch
):
    from tests.test_appserver_history import _FakeSource, _patch_source

    _patch_source(monkeypatch, _FakeSource())
    lines = []
    session = _session(tmp_path, lines)
    session._transcript_store.record_user("old task")
    session._transcript_store.record_visible_tool(_public_event(), identifier="old-tool")
    await session.handle(
        Request("resume", "gecmis.surdur", {"kaynak": "claude", "oturum_id": "s1"})
    )
    await session.handle(Request("history", "oturum.gecmis", {}))
    rows = _sonuc(lines, "history")["mesajlar"]
    assert not any(row["rol"] == "olay" for row in rows)
    assert rows[0]["metin"] == "oyun yap"
    await session.close()

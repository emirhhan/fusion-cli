from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.response_actions import fork_response, save_rating
from fusion_cli.cli.repl.transcript_store import load_transcript_messages
from fusion_cli.core.types import Message


def test_fork_persists_only_messages_through_selected_response(tmp_path):
    history = [
        Message("user", "ilk soru"),
        Message("assistant", "ilk yanıt"),
        Message("user", "sonraki soru"),
        Message("assistant", "sonraki yanıt"),
    ]
    result = fork_response(
        tmp_path / "memory", tmp_path, "source", history, {"metin": "ilk yanıt", "eslesme": 0}
    )
    assert result["ok"] is True
    restored = load_transcript_messages(
        tmp_path / "memory", tmp_path, conversation_id=result["sohbet_id"]
    )
    assert [message.content for message in restored] == ["ilk soru", "ilk yanıt"]
    assert len(history) == 4


def test_fork_rejects_unknown_boundary_without_creating_history(tmp_path):
    result = fork_response(
        tmp_path, tmp_path, "source", [Message("user", "hi")], {"metin": "unknown"}
    )
    assert result["ok"] is False
    assert not (tmp_path / "transcripts").exists()


def test_fork_uses_persisted_visible_response_when_context_differs(tmp_path):
    from fusion_cli.cli.repl.transcript_store import TranscriptStore

    base = tmp_path / "memory"
    store = TranscriptStore(base, tmp_path, conversation_id="source")
    store.record_user("question")
    store.record_assistant("İptal edildi.")
    result = fork_response(
        base,
        tmp_path,
        "source",
        [Message("user", "question"), Message("assistant", "internal cancellation context")],
        {"metin": "İptal edildi."},
    )
    assert result["ok"] is True
    assert [
        m.content
        for m in load_transcript_messages(base, tmp_path, conversation_id=result["sohbet_id"])
    ] == ["question", "İptal edildi."]


def test_rating_is_local_metadata_without_answer_content(tmp_path):
    result = save_rating(tmp_path, "chat", {"metin": "private answer", "rating": "positive"})
    assert result["ok"] is True
    path = tmp_path / "feedback" / "response-ratings.jsonl"
    text = path.read_text()
    assert "private answer" not in text
    assert json.loads(text)["rating"] == "positive"


@pytest.mark.parametrize("rating", [None, "other", 1])
def test_rating_rejects_invalid_values(tmp_path, rating):
    assert save_rating(tmp_path, "chat", {"metin": "answer", "rating": rating})["ok"] is False


def test_fork_selects_duplicate_response_occurrence(tmp_path):
    history = [
        Message("user", "one"),
        Message("assistant", "same"),
        Message("user", "two"),
        Message("assistant", "same"),
    ]
    result = fork_response(
        tmp_path / "memory", tmp_path, "source", history, {"metin": "same", "eslesme": 1}
    )
    assert result["ok"] is True
    assert result["mesaj_sayisi"] == 4


def test_fork_at_journal_limit_preserves_source(tmp_path):
    from fusion_cli.cli.repl import transcript_store

    base = tmp_path / "memory"
    source = transcript_store.TranscriptStore(base, tmp_path, conversation_id="source")
    source.record_user("question")
    source.record_assistant("answer")
    with source.events_path.open("a") as stream:
        stream.write(
            json.dumps({"event": "ToolStarted", "session_id": "source", "details": "x" * 8_000_000})
            + "\n"
        )
    history = load_transcript_messages(base, tmp_path, conversation_id="source")
    result = fork_response(base, tmp_path, "source", history, {"metin": "answer"})
    assert result["ok"] is True
    assert [
        m.content for m in load_transcript_messages(base, tmp_path, conversation_id="source")
    ] == ["question", "answer"]
    assert [
        m.content
        for m in load_transcript_messages(base, tmp_path, conversation_id=result["sohbet_id"])
    ] == ["question", "answer"]


@pytest.mark.asyncio
async def test_fork_rpc_can_reopen_persisted_branch(tmp_path):
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    output = []
    session = AppSession(output.append, root=tmp_path, home=tmp_path / "home")
    session._state.history = [Message("user", "question"), Message("assistant", "answer")]
    await session.handle(Request(id="fork", name="sohbet.dallan", data={"metin": "answer"}))
    result = json.loads(output[-1])["veri"]
    assert result["ok"] is True
    await session.handle(
        Request(id="open", name="oturum.baslat", data={"sohbet_id": result["sohbet_id"]})
    )
    assert [message.content for message in session._state.history] == ["question", "answer"]

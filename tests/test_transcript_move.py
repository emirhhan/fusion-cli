"""Sohbet taşınırken geçmiş kaybolmaz ve yanlış proje silinmez."""

from pathlib import Path

import pytest

from fusion_cli.cli.repl.transcript_store import (
    TranscriptStore,
    list_conversations,
    load_transcript_messages,
    move_conversation,
)


def test_sohbet_diger_projenin_gecmisine_tasinir(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    store = TranscriptStore(tmp_path / "memory", source, conversation_id="chat-1")
    store.record_user("Bir uygulama geliştir")
    store.record_assistant("İlk adımı yaptım")

    move_conversation(tmp_path / "memory", source, target, "chat-1")

    assert list_conversations(tmp_path / "memory", source) == ()
    assert [ref.conversation_id for ref in list_conversations(tmp_path / "memory", target)] == [
        "chat-1"
    ]
    assert [message.content for message in load_transcript_messages(
        tmp_path / "memory", target, conversation_id="chat-1"
    )] == ["Bir uygulama geliştir", "İlk adımı yaptım"]


def test_sohbet_hedef_yoksa_kaynagi_korur(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    store = TranscriptStore(tmp_path / "memory", source, conversation_id="chat-1")
    store.record_user("Önemli sohbet")

    with pytest.raises(ValueError, match="Hedef proje klasörü"):
        move_conversation(tmp_path / "memory", source, tmp_path / "missing", "chat-1")
    assert [ref.conversation_id for ref in list_conversations(tmp_path / "memory", source)] == [
        "chat-1"
    ]

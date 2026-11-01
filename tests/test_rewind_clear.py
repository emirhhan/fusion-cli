"""`/clear` öncesi oturuma `/rewind` ile dönüş (#200)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.appserver.commands import command_choices
from fusion_cli.cli.repl import rewind, rewind_clear
from fusion_cli.cli.repl.session_clear import clear_command
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    root = tmp_path / "proje"
    root.mkdir()
    return ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=root,
        home=tmp_path / "ev",
    )


def _konusma(state: ReplState) -> str:
    store = TranscriptStore(
        state.config.memory_dir, state.root, conversation_id=state.conversation_id
    )
    store.record_user("eski soru")
    store.record_assistant("eski cevap")
    state.history = [Message("user", "eski soru"), Message("assistant", "eski cevap")]
    return state.conversation_id


def test_clear_sonrasi_menude_onceki_oturum_satiri(state: ReplState, monkeypatch):
    eski = _konusma(state)
    clear_command(state, "")
    satirlar = rewind_clear.previous_session_choices(state)
    assert [c.value for c in satirlar] == [f"resume:{eski}"]
    assert satirlar[0].label == f"/resume {eski} (önceki oturum)"
    # Masaüstü seçicisi de aynı satırı başta gösterir.
    payload = command_choices(state, "rewind", "")
    assert payload is not None and payload["secenekler"][0]["deger"] == f"resume:{eski}"
    # Satır içi seçici: seçilince `/clear` öncesi sohbet sürdürülür.
    monkeypatch.setattr(rewind, "pick", lambda choices, title: choices[0].value)
    rewind.rewind_command(state, "")
    assert state.conversation_id == eski
    assert [m.content for m in state.history][:1] == ["eski soru"]
    # Başka sohbete geçildi: öneri kaybolur.
    assert rewind_clear.previous_session_choices(state) == []


def test_bos_sohbette_clear_oneri_birakmaz(state: ReplState):
    clear_command(state, "")
    assert rewind_clear.previous_session_choices(state) == []
    assert rewind.rewind_command(state, "") == rewind.messages.REWIND_NOTHING

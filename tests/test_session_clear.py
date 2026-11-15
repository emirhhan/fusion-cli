"""`/clear [ad]` yeni boş sohbet açar; `/reset` ve `/new` takma addır (#185)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl.commands import RENDERED_COMMANDS, build_registry, parse
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.transcript_store import (
    TranscriptStore,
    find_conversation,
    list_conversations,
)
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    config = make_config(memory_dir=tmp_path / "bellek")
    root = tmp_path / "proje"
    root.mkdir()
    return ReplState(config=config, memory=null_memory(), root=root, home=tmp_path / "ev")


def _run(state: ReplState, line: str) -> str:
    name, argument = parse(line)
    command = build_registry().get(name)
    assert command is not None, line
    assert command.name == "clear"
    return command.handler(state, argument)


def _seed(state: ReplState) -> str:
    store = TranscriptStore(
        state.config.memory_dir, state.root, conversation_id=state.conversation_id
    )
    store.record_user("oyun yaz")
    store.record_assistant("tamam")
    state.history = [Message(role="user", content="oyun yaz"), Message("assistant", "tamam")]
    return state.conversation_id


@pytest.mark.parametrize("line", ["/clear", "/reset", "/new"])
def test_clear_yeni_sohbet_kimligi_acar_eskisi_surdurulebilir(state, line):
    old_id = _seed(state)

    note = _run(state, line)

    assert state.history == []
    assert state.conversation_id != old_id
    assert "/resume" in note
    ref = find_conversation(state.config.memory_dir, state.root, old_id)
    assert ref is not None and ref.message_count == 2


def test_clear_argumani_birakilan_sohbete_ad_verir(state):
    old_id = _seed(state)

    _run(state, "/clear Oyun projesi")

    (ref,) = list_conversations(state.config.memory_dir, state.root)
    assert ref.conversation_id == old_id
    assert ref.name == "Oyun projesi"
    assert state.conversation_name == ""


def test_clear_ekran_basan_komut_degil():
    assert "clear" not in RENDERED_COMMANDS
    assert build_registry().get("reset").name == "clear"

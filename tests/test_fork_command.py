"""`/fork [istem]` (#229): konuşmayı arka plan kopyasına verir, bu sohbet değişmez."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl import agent_link
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.transcript_store import list_conversations
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools import agent_tasks
from fusion_cli.ui import messages

from .fakes import make_config


@pytest.fixture
def launches(monkeypatch):
    calls: list[list[str]] = []

    def _fake(argv, cwd, log, err) -> int:
        calls.append(argv)
        return 4321

    monkeypatch.setattr(agent_tasks, "spawn_detached", _fake)
    return calls


@pytest.fixture
def state(tmp_path: Path):
    value = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    value.history = [Message("user", "API istemcisini yaz"), Message("assistant", "Başladım")]
    yield value
    agent_link.close_link(value)


def _fork(state: ReplState, argument: str) -> str:
    command = build_registry().get("fork")
    assert command is not None
    return command.handler(state, argument)


def test_istemli_fork_konusmayi_devralan_arka_plan_gorevi_baslatir(state, launches) -> None:
    once = list(state.history)

    sonuc = _fork(state, "taslak PR aç")

    task = agent_tasks.task_store(state.config.memory_dir).tasks()[0]
    assert task.prompt == "taslak PR aç"
    assert task.owner == state.conversation_id
    stored = agent_tasks.task_store(state.config.memory_dir).load_history(task.id)
    assert [item["content"] for item in stored] == ["API istemcisini yaz", "Başladım"]
    assert task.id in sonuc and messages.FORK_IN_PLACE.strip() in sonuc
    assert state.history == once and launches


def test_istemsiz_fork_bekleyen_kayitli_kopya_olusturur(state, launches) -> None:
    sonuc = _fork(state, "")

    refs = list_conversations(state.config.memory_dir, state.root)
    assert len(refs) == 1 and refs[0].conversation_id != state.conversation_id
    assert refs[0].conversation_id in sonuc
    assert launches == []


def test_bos_konusmada_fork_reddedilir(state, launches) -> None:
    state.history = []
    assert _fork(state, "iş") == messages.FORK_EMPTY
    assert launches == []

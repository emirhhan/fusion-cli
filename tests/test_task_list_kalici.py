"""Görev listesi oturum boyu yaşar, sürdürmede geri gelir, liste kimliğiyle paylaşılır (#331).

Claude Code (interactive-mode › Task list): liste oturum boyunca kalır ve `--resume` ile geri
gelir; `CLAUDE_CODE_TASK_LIST_ID` ile `~/.claude/tasks/<ad>` üzerinden oturumlar paylaşır.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.cli.repl import task_list
from fusion_cli.cli.repl.loop import _turn_tool_context
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.planning import todo_write

from .fakes import make_config


def _state(tmp_path: Path, conversation: str = "session-a") -> ReplState:
    return ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
        conversation_id=conversation,
    )


_LISTE = {"todos": [{"content": "testi yaz", "status": "in_progress"}]}


def test_liste_turlar_arasinda_kalir(tmp_path, monkeypatch):
    monkeypatch.delenv(task_list.TASK_LIST_ID_ENV, raising=False)
    state = _state(tmp_path)
    todo_write(_LISTE, _turn_tool_context(state))
    ikinci_tur = _turn_tool_context(state)
    assert [item.content for item in ikinci_tur.todos.items] == ["testi yaz"]


def test_surdurulen_sohbet_listeyi_geri_getirir(tmp_path, monkeypatch):
    monkeypatch.delenv(task_list.TASK_LIST_ID_ENV, raising=False)
    todo_write(_LISTE, _turn_tool_context(_state(tmp_path, "session-eski")))
    yeni = _state(tmp_path, "session-yeni")
    assert _turn_tool_context(yeni).todos.items == ()
    yeni.conversation_id = "session-eski"  # /resume
    assert len(_turn_tool_context(yeni).todos.items) == 1


def test_liste_kimligi_oturumlar_arasinda_paylasilir(tmp_path, monkeypatch):
    monkeypatch.setenv(task_list.TASK_LIST_ID_ENV, "ortak")
    birinci, ikinci = _state(tmp_path, "session-1"), _state(tmp_path, "session-2")
    todo_write(_LISTE, _turn_tool_context(birinci))
    assert len(_turn_tool_context(ikinci).todos.items) == 1
    claude_dir = Path(__import__("os").environ["CLAUDE_CONFIG_DIR"])
    assert (claude_dir / "tasks" / "ortak" / "fusion-todos.json").is_file()


def test_bozuk_dosya_bos_liste(tmp_path, monkeypatch):
    monkeypatch.delenv(task_list.TASK_LIST_ID_ENV, raising=False)
    state = _state(tmp_path)
    path = task_list.task_list_path(state.config.memory_dir, state.conversation_id)
    path.parent.mkdir(parents=True)
    path.write_text("{bozuk", encoding="utf-8")
    assert _turn_tool_context(state).todos.items == ()


def test_onceki_turdan_kalan_bekleyen_madde_otomatik_devami_tetiklemez(tmp_path, monkeypatch):
    monkeypatch.delenv(task_list.TASK_LIST_ID_ENV, raising=False)
    state = _state(tmp_path)
    birinci = _turn_tool_context(state)
    todo_write(_LISTE, birinci)
    assert birinci.todos.has_pending
    ikinci = _turn_tool_context(state)
    assert ikinci.todos.items and not ikinci.todos.has_pending

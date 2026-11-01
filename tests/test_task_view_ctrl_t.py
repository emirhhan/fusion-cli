"""Ctrl+T görev listesi görünümü (Claude Code interactive-mode › Task list, #330)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl import task_view
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.task_list import session_todos
from fusion_cli.cli.repl.tui import FusionTui
from fusion_cli.config import keybindings
from fusion_cli.config.loader import load_config
from fusion_cli.core.tools import TodoItem, TodoStatus
from fusion_cli.memory.factory import null_memory


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def test_ctrl_t_varsayilan_iki_baglamda():
    table = keybindings.load_keymap(Path("/yok/keybindings.json"))
    assert table.bindings(keybindings.CONTEXT_TUI)["c-t"] == "gorev_listesi"
    assert table.bindings(keybindings.CONTEXT_INPUT)["c-t"] == "gorev_listesi"


def test_en_cok_bes_madde_suren_ve_bekleyen_once(state: ReplState):
    todos = session_todos(state)
    todos.replace(
        tuple(TodoItem(f"bitti {i}", TodoStatus.COMPLETED) for i in range(3))
        + tuple(TodoItem(f"bekliyor {i}", TodoStatus.PENDING) for i in range(3))
        + (TodoItem("yazılıyor", TodoStatus.IN_PROGRESS, "Kod yazılıyor"),)
    )

    lines = task_view.task_lines(state)

    assert lines[0] == "▶ Kod yazılıyor"
    assert lines[1:4] == ["☐ bekliyor 0", "☐ bekliyor 1", "☐ bekliyor 2"]
    assert len(lines) == 6 and lines[-1] == "… +2 görev daha"


def test_bos_liste_ve_gorunurluk_surdurmede_kalir(state: ReplState):
    assert task_view.task_lines(state) == ["Görev listesi boş"]
    assert task_view.is_visible(state) is False
    assert task_view.toggle_visible(state) is True

    resumed = ReplState(config=state.config, memory=null_memory(), root=state.root, home=state.home)
    resumed.conversation_id = state.conversation_id
    assert task_view.is_visible(resumed) is True
    assert task_view.toggle_visible(resumed) is False


def test_tui_ctrl_t_listeyi_acar_kapatir():
    calls: list[bool] = []
    visible = {"v": False}

    def toggle() -> bool:
        visible["v"] = not visible["v"]
        calls.append(visible["v"])
        return visible["v"]

    tui = FusionTui(
        on_submit=lambda _line: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
        on_toggle_tasks=toggle,
        task_lines=lambda: ["☐ a"],
    )
    assert tui._task_fragments() == [("class:work", "  ☐ a")]
    tui._toggle_tasks()
    assert tui._tasks_visible is True and calls == [True]
    tui._toggle_tasks()
    assert tui._tasks_visible is False

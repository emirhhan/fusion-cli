"""`vimInsertModeRemaps` ve statusline `vim.mode` (#217)."""

from __future__ import annotations

import json
from pathlib import Path

from prompt_toolkit.key_binding import KeyBindings

from fusion_cli.cli.repl import vim_remaps
from fusion_cli.cli.repl.tui import FusionTui


def test_yalniz_gecerli_iki_karakterli_esc_hedefi(tmp_path: Path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"vimInsertModeRemaps": {"jj": "<Esc>", "jjj": "<Esc>", "kj": "x"}}),
        encoding="utf-8",
    )
    assert vim_remaps.load_remaps(tmp_path) == ("jj",)
    assert vim_remaps.load_remaps(tmp_path / "yok") == ()


class _Doc:
    def __init__(self, buffer) -> None:
        self._buffer = buffer

    @property
    def text_before_cursor(self) -> str:
        return self._buffer.text


class _Buffer:
    def __init__(self) -> None:
        self.text = ""

    @property
    def document(self):
        return _Doc(self)

    def insert_text(self, text: str) -> None:
        self.text += text

    def delete_before_cursor(self, count: int) -> None:
        self.text = self.text[:-count]


class _ViState:
    input_mode = None


class _Event:
    def __init__(self, buffer, app) -> None:
        self.current_buffer = buffer
        self.app = app


class _App:
    def __init__(self) -> None:
        self.vi_state = _ViState()


def test_ikinci_tus_pencere_icinde_normale_gecer(tmp_path: Path):
    from prompt_toolkit.key_binding.vi_state import InputMode

    now = [0.0]
    kb = KeyBindings()
    vim_remaps.add_remap_bindings(kb, ("jk",), clock=lambda: now[0])
    handlers = {b.keys[0]: b.handler for b in kb.bindings}
    buffer, app = _Buffer(), _App()
    handlers["j"](_Event(buffer, app))
    handlers["k"](_Event(buffer, app))
    assert buffer.text == "" and app.vi_state.input_mode == InputMode.NAVIGATION
    app = _App()
    handlers["j"](_Event(buffer, app))
    now[0] = 2.0
    handlers["k"](_Event(buffer, app))
    assert buffer.text == "jk" and app.vi_state.input_mode is None


def test_tui_vim_kip_adi():
    tui = FusionTui(
        on_submit=lambda _t: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )
    tui.set_vim(True)
    tui.set_vim_remaps(("jj",))
    assert tui.vim_mode_name() in ("INSERT", "NORMAL")
    keys = {
        tuple(str(getattr(k, "value", k)) for k in b.keys)
        for b in tui.application.key_bindings.bindings
    }
    assert ("j",) in keys

"""Tam ekran döngünün #216 genel kısayol bağlantıları.

`FusionTui.extras` tuşları karşılar; bu sınıf onları oturum durumuna bağlar:
Ctrl+O transcript kaynağı (`ReplState.history`), Ctrl+V görüntü çipleri (oturum bellek
dizini), Option+P/T/O eylemleri ve tur sonunda boş girdiye istem önerisi.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from typing import TYPE_CHECKING

from rich.markup import escape

from ...ui import theme
from . import option_keys, prompt_suggestion, transcript_view
from .clipboard_image import ImageChips

if TYPE_CHECKING:
    from .state import ReplState
    from .tui import FusionTui

#: Option eylemi → gönderilen slash komutu (girdideki taslak korunur).
OPTION_COMMANDS = {"model_sec": "/model", "dusunme": "/thinking"}


def option_command(action: str) -> str | None:
    return OPTION_COMMANDS.get(action)


class TuiShortcuts:
    def __init__(
        self,
        state: ReplState,
        tui: FusionTui,
        submit: Callable[[str], None],
        echo: Callable[[object], None],
    ) -> None:
        self._state = state
        self._tui = tui
        self._submit = submit
        self._echo = echo
        self._suggestions = prompt_suggestion.SuggestionSink()
        extras = tui.extras
        extras.transcript_source = self.transcript
        extras.option_handler = self.option
        extras.image_chips = ImageChips(state.config.memory_dir / "pastes")

    def transcript(self, show_all: bool) -> str:
        width = shutil.get_terminal_size((100, 30)).columns
        return transcript_view.render(self._state.history, width=width, show_all=show_all)

    def option(self, action: str) -> None:
        command = option_command(action)
        if command is not None:
            self._submit(command)
        elif action == "hizli_kip":
            self._echo(f"[{theme.DIM}]{escape(option_keys.FAST_UNAVAILABLE)}[/{theme.DIM}]")

    def take_images(self, line: str) -> tuple[str, ...]:
        chips = self._tui.extras.image_chips
        return chips.take(line) if chips is not None else ()

    def begin_turn(self) -> prompt_suggestion.SuggestionSink:
        self._suggestions.reset()
        return self._suggestions

    def finish_turn(self) -> None:
        text = self._suggestions.take()
        if text and prompt_suggestion.enabled(self._state.root, self._state.home):
            self._tui.offer_suggestion(text)

"""Satır içi REPL'in #216 genel kısayolları (tam ekran TUI'deki karşılıklarıyla aynı eylemler).

Claude Code interactive-mode "General controls": Ctrl+O transcript, Ctrl+T görev listesi,
Ctrl+V görüntü yapıştırma, Ctrl+X Ctrl+K arka plan ajanlarını durdurma, boş girdide `?`
kısayol paneli, Option+P model seçici, Option+T düşünme, Option+O hızlı kip; yanıttan sonra
boş girdide istem önerisi (Tab/Sağ ok kabul eder).

Satır içi istem yalnız tur aralarında açıktır; buradaki çıktılar istemin ÜSTÜNE basılır
(`prompt_toolkit.application.run_in_terminal`), yazılan taslak korunur.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.text import Text

from ...ui import messages, theme
from . import option_keys, prompt_suggestion, transcript_view
from .clipboard_image import NO_IMAGE, ImageChips
from .tui_input_keys import KILL_AGENTS_WINDOW_S, DoublePress
from .tui_shortcuts import option_command

if TYPE_CHECKING:
    from prompt_toolkit.key_binding import KeyPressEvent

    from .input import ReplInput
    from .state import ReplState

Action = Callable[[Any], None]


def todo_lines(state: ReplState) -> str:
    """Son turun görev listesi (Ctrl+T); boşsa kısa not."""
    todos = getattr(state.last_tool_context, "todos", None)
    items = todos.items if todos is not None else ()
    marks = {"pending": "☐", "in_progress": "◐", "completed": "☑"}
    lines = [f"  {marks.get(item.status.value, '☐')} {item.content}" for item in items]
    return "\n".join(lines) or messages.TODOS_EMPTY


class InlineShortcuts:
    def __init__(self, state: ReplState, console: Console) -> None:
        self._state = state
        self._console = console
        self.image_chips = ImageChips(state.config.memory_dir / "pastes")
        self.suggestions = prompt_suggestion.SuggestionSink()
        self._kill_press = DoublePress(KILL_AGENTS_WINDOW_S)
        self._tasks: set[asyncio.Future[None]] = set()

    def _print(self, text: str, *, ansi: bool = False) -> None:
        from prompt_toolkit.application import run_in_terminal

        def _write() -> None:
            body = Text.from_ansi(text) if ansi else Text(text, style=theme.DIM)
            self._console.print(body)

        run_in_terminal(_write)

    def actions(self, owner: ReplInput) -> dict[str, Action]:
        """Satır içi istem eylemleri (bkz. `input.build_input_bindings`)."""
        return {
            "transkript": lambda _event: self._print(self.transcript(), ansi=True),
            "gorevler": lambda _event: self._print(todo_lines(self._state)),
            "gorsel_yapistir": self._paste_image,
            "ajanlari_durdur": lambda _event: self._kill_agents(),
            "kisayollar": self._shortcuts,
            "model_sec": lambda event: self._option(owner, "model_sec", event),
            "dusunme": lambda event: self._option(owner, "dusunme", event),
            "hizli_kip": lambda event: self._option(owner, "hizli_kip", event),
        }

    def transcript(self) -> str:
        width = shutil.get_terminal_size((100, 30)).columns
        return transcript_view.render(self._state.history, width=width)

    def _paste_image(self, event: KeyPressEvent) -> None:
        chip = self.image_chips.paste()
        if chip is None:
            self._print(NO_IMAGE)
            return
        event.current_buffer.insert_text(chip)

    def _shortcuts(self, event: KeyPressEvent) -> None:
        """Boş girdide `?` paneli; yazı varken `?` karakteri yazılır."""
        if event.current_buffer.text:
            event.current_buffer.insert_text("?")
            return
        self._print(messages.SHORTCUTS_PANEL)

    def _kill_agents(self) -> None:
        if not self._kill_press.press():
            self._print(messages.KILL_AGENTS_CONFIRM)
            return

        async def _stop() -> None:
            count = await self._state.child_runs.cancel_background()
            self._print(messages.KILL_AGENTS_DONE.format(count=count))

        future = asyncio.ensure_future(_stop())
        self._tasks.add(future)
        future.add_done_callback(self._tasks.discard)

    def _option(self, owner: ReplInput, action: str, event: KeyPressEvent) -> None:
        command = option_command(action)
        if command is None:
            self._print(option_keys.FAST_UNAVAILABLE)
            return
        # Claude Code: Option+P modeli "girdiyi temizlemeden" değiştirir; taslak geri gelir.
        owner.run_bound_command(command, event, keep_draft=True)

    def take_images(self, line: str) -> tuple[str, ...]:
        return self.image_chips.take(line)

    def next_suggestion(self) -> str:
        text = self.suggestions.take()
        if text and prompt_suggestion.enabled(self._state.root, self._state.home):
            return text
        return ""

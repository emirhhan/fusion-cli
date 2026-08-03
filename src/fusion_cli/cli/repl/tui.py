"""Ink-benzeri tek yol REPL çrome'u — `prompt_toolkit` `Application(full_screen=False)`.

Claude Code modeli: normal tampon (alternatif ekran YOK → scrollback korunur), en altta
pinli çerçeveli girdi kutusu ve hemen altında durum satırı. Motor çıktısı girdinin
ÜSTÜNE, gerçek terminale akar (`run_in_terminal`); spinner alt-chrome'da pinli kalır.
Tuşlar tur boyunca canlı okunur: esc/Ctrl-C turu keser, shift-tab mod döndürür, Enter
gönderir.

Bu modül SUNUM ve TUŞ yönlendirmesidir; iş mantığı callback'lerle dışarıdadır (test
edilebilirlik: TTY olmadan kurulup mantığı sınanabilir).
"""

from __future__ import annotations

from collections.abc import Callable

from prompt_toolkit.application import Application, run_in_terminal
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame, TextArea

from ...ui import messages, theme

#: Girdi kutusunun içindeki istem işareti (Claude Code `> `).
PROMPT = "> "

#: Onay modunun durum satırındaki rengi — riskli mod göze çarpsın.
_MODE_COLORS = {"auto": theme.OK, "plan": theme.WARN, "security": theme.ERROR}


def format_status(mode: str, engine: str) -> str:
    """Girdinin ALTINDAKİ durum satırının HTML'i: mod + motor + kısayol ipuçları.

    Auto/plan/security modu artık istem satırının içinde değil, burada — Claude Code'da
    olduğu gibi girdinin hemen altında.
    """
    color = _MODE_COLORS.get(mode, theme.DIM)
    return (
        f"<style fg='{color}'>{theme.ICON_STATUS} {mode}</style>"
        f"<style fg='{theme.DIM}'> · {engine} · {messages.TUI_STATUS_HINT}</style>"
    )


class FusionTui:
    """Alt-chrome'u çizen ve tuşları callback'lere yönlendiren tek yol REPL görünümü."""

    def __init__(
        self,
        *,
        on_submit: Callable[[str], None],
        on_interrupt: Callable[[], None],
        on_exit: Callable[[], None],
        on_cycle_mode: Callable[[], None],
    ) -> None:
        self._on_submit = on_submit
        self._on_interrupt = on_interrupt
        self._on_exit = on_exit
        self._on_cycle_mode = on_cycle_mode
        self._work_text = ""
        self._status_html = ""

        self._input = TextArea(
            height=1, multiline=False, wrap_lines=False, prompt=PROMPT, accept_handler=self._accept
        )
        # Çalışma satırı yalnızca bir tur çalışırken görünür; boşken yer kaplamaz.
        work_window = ConditionalContainer(
            Window(FormattedTextControl(lambda: self._work_text), height=1),
            filter=Condition(lambda: bool(self._work_text)),
        )
        status_window = Window(FormattedTextControl(lambda: HTML(self._status_html)), height=1)
        root = HSplit([work_window, Frame(self._input), status_window])
        self.application: Application[None] = Application(
            layout=Layout(root, focused_element=self._input),
            key_bindings=self._bindings(),
            full_screen=False,
            mouse_support=False,
        )

    # -- Dışarıdan beslenen durum ------------------------------------------- #

    def set_work(self, text: str) -> None:
        """Spinner/çalışma satırını güncelle (pinli alt-chrome'da)."""
        self._work_text = text
        self._invalidate()

    def clear_work(self) -> None:
        self._work_text = ""
        self._invalidate()

    def set_status(self, mode: str, engine: str) -> None:
        """Girdinin altındaki durum satırını güncelle."""
        self._status_html = format_status(mode, engine)
        self._invalidate()

    async def print_above(self, render: Callable[[], None]) -> None:
        """Girdinin ÜSTÜNE, gerçek terminale bas; alt-chrome sonra yeniden çizilir."""
        await run_in_terminal(render)

    def request_exit(self) -> None:
        if self.application.is_running:
            self.application.exit()

    # -- Tuş yönlendirmesi -------------------------------------------------- #

    def _accept(self, buffer: object) -> bool:
        """Enter: satırı callback'e ver, tamponu temizle (False → içerik silinir)."""
        text = getattr(buffer, "text", "")
        self._on_submit(text)
        return False

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-q")
        def _exit(_event: object) -> None:
            self._on_exit()

        @kb.add("escape", eager=True)
        @kb.add("c-c")
        def _interrupt(_event: object) -> None:
            # Tur çalışıyorsa keser; boştaysa callback girdiyi temizlemeyi seçebilir.
            self._on_interrupt()

        @kb.add("s-tab")
        def _cycle(_event: object) -> None:
            self._on_cycle_mode()

        return kb

    def _invalidate(self) -> None:
        if self.application.is_running:
            self.application.invalidate()

"""SPIKE (commit edilmez) — ANSI renkli konuşma + tekerlek kaydırma denemesi.

Soru: spike4 reçetesi (mouse_support=False + ?1h app-cursor + İMLEÇ-tabanlı
kaydırma) `FormattedTextControl(ANSI(...))` içerikli renkli bir konuşma
kontrolüyle birleşince tekerlek HÂLÂ kaydırıyor mu?

Bu dosya üretim değildir; Faz 4 Task 2 kararı verilince silinir. Mevcut
screen.py / ansi_bridge.py'a DOKUNMAZ; onların yanında ayrı bir kabuk kurar.

Çalıştırma (gerçek Terminal.app, yeni sekme):
    FUSION_FULLSCREEN=1 FUSION_SPIKE=1 fusion

Gözlenecekler:
- markdown/kod renkli mi görünüyor (ham \\x1b kaçışı DEĞİL)?
- fare tekerleği konuşmayı kaydırıyor mu? ok / PageUp?
- pencere resize'da ❯ çoğalması / scrollback sızması var mı?
- Ctrl-Q sonrası terminal normale dönüyor mu?
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame, TextArea
from rich.console import Console

if TYPE_CHECKING:
    from .state import ReplState


class _RenkliKopru:
    """AnsiBridge'in renkli versiyonu: force_terminal=True → SGR kodları üretir."""

    def __init__(self) -> None:
        self._buffer = io.StringIO()
        # force_terminal=True: Rich renkli SGR yayar. color_system standart tut.
        self._console = Console(
            file=self._buffer, force_terminal=True, color_system="standard", soft_wrap=True
        )
        self._text = ""
        self._okundu = 0

    @property
    def console(self) -> Console:
        return self._console

    @property
    def text(self) -> str:
        return self._text

    def drain(self) -> str:
        tumu = self._buffer.getvalue()
        delta = tumu[self._okundu :]
        self._okundu = len(tumu)
        self._text += delta
        return delta


_SCROLL_STEP = 1
_SCROLL_PAGE = 8
_BANNER = "  ✦ fusion — SPIKE renkli konuşma · çıkış: Ctrl-Q"


class _SpikeScreen:
    """Renkli konuşma kontrollü deneme kabuğu.

    Konuşma alanı `FormattedTextControl(ANSI(...))` — ham metin ANSI olarak çözülür.
    Kaydırma İMLEÇ yerine `vertical_scroll` üzerinden değil; ANSI kontrolünde imleç
    kavramı yok, bu yüzden görünür kaydırma ofsetini kendimiz tutup pencereye
    `get_vertical_scroll` ile veriyoruz. Tekerlek ?1h ile ok tuşu olarak geldiği
    için ok bağlamaları tekerleği de kapsar.
    """

    def __init__(self) -> None:
        self._bridge = _RenkliKopru()
        self._scroll = 0
        self._follow = True

        self._conv_window = Window(
            content=FormattedTextControl(lambda: ANSI(self._bridge.text)),
            wrap_lines=True,
            get_vertical_scroll=lambda win: self._scroll,
            always_hide_cursor=True,
        )
        self._input = TextArea(height=1, prompt="❯ ", multiline=False, wrap_lines=False)
        self._input.accept_handler = self._submit

        root = HSplit(
            [
                Window(content=FormattedTextControl(_BANNER), height=3),
                Frame(self._conv_window, title="konuşma (renkli spike)"),
                Frame(self._input, title="mesaj"),
            ]
        )
        self.application: Application[Any] = Application(
            layout=Layout(root, focused_element=self._input),
            key_bindings=self._bindings(),
            full_screen=True,
            mouse_support=False,
        )
        self._on_submit: Any = lambda t: None

    @property
    def bridge(self) -> _RenkliKopru:
        return self._bridge

    def set_work(self, text: str) -> None:
        # Spike'ta ayrı çalışma satırı yok; başlığa/konuşmaya karışmasın diye yut.
        self.application.invalidate()

    def clear_work(self) -> None:
        self.application.invalidate()

    def _satir_sayisi(self) -> int:
        return max(1, self._bridge.text.count("\n") + 1)

    def after_event(self) -> None:
        self._bridge.drain()
        if self._follow:
            # Alta yapış: en son satırları göster (kaba tahmin; render clamp'ler).
            self._scroll = max(0, self._satir_sayisi() - 1)
        self.application.invalidate()

    def _kaydir(self, delta: int) -> None:
        self._scroll = max(0, min(self._satir_sayisi() - 1, self._scroll + delta))
        self._follow = self._scroll >= self._satir_sayisi() - 1
        self.application.invalidate()

    def _submit(self, _buff: Any) -> bool:
        text = self._input.text.strip()
        self._input.text = ""
        if text:
            self._on_submit(text)
        return False

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-q")
        @kb.add("c-c")
        def _exit(event: Any) -> None:
            event.app.exit()

        _girisd_disi = Condition(lambda: True)

        @kb.add("up", filter=_girisd_disi, eager=True)
        def _up(_e: Any) -> None:
            self._kaydir(-_SCROLL_STEP)

        @kb.add("down", filter=_girisd_disi, eager=True)
        def _down(_e: Any) -> None:
            self._kaydir(+_SCROLL_STEP)

        @kb.add("pageup", eager=True)
        def _pgup(_e: Any) -> None:
            self._kaydir(-_SCROLL_PAGE)

        @kb.add("pagedown", eager=True)
        def _pgdn(_e: Any) -> None:
            self._kaydir(+_SCROLL_PAGE)

        return kb


async def run_spike(state: ReplState) -> int:
    """Renkli-konuşma spike'ını gerçek motorla çalıştır (elle doğrulama)."""
    import asyncio
    import sys

    from .screen import APP_CURSOR_OFF, install_app_cursor_mode
    from .screen_turn import run_turn

    screen = _SpikeScreen()

    turn_tasks: set[asyncio.Task[None]] = set()

    def _start(text: str) -> None:
        # screen_turn.run_turn FusionScreen bekliyor; spike ekranı da bridge +
        # after_event + set_work/clear_work sunmalı. Eksik olanları köprüle.
        task = asyncio.ensure_future(run_turn(text, state, screen))  # type: ignore[arg-type]
        turn_tasks.add(task)
        task.add_done_callback(turn_tasks.discard)

    screen._on_submit = _start
    install_app_cursor_mode(screen.application)
    try:
        await screen.application.run_async()
    finally:
        sys.stdout.write(APP_CURSOR_OFF)
        sys.stdout.flush()
    return 0

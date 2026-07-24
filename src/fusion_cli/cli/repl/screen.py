"""Tam-ekran (alternatif ekran) kabuk — doğrulanmış reçeteyle.

Neden alternatif ekran: normal tamponda terminal resize'ı prompt_toolkit'in bayat
imleç modeliyle yaptığı silmeyi ıskalatıp giriş işareti kopyaları biriktiriyordu
ve yukarı kaydırınca eski shell çıktısı görünüyordu. Ekranı uygulama sahiplenince
bu sınıf hatalar ortadan kalkar.

Reçete (gerçek Terminal.app'te ölçülerek doğrulandı):
- full_screen=True (alternatif ekran)
- mouse_support=False (agresif fare takibi resize'ı bozuyor)
- reset_cursor_key_mode → uygulama imleç modu (tekerlek = ok tuşu, scrollback'e kaçmaz)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame, TextArea

#: Uygulama imleç + keypad modu (DECCKM + DECKPAM). Terminal.app tekerleği ok
#: tuşuna çevirip uygulamaya yollar; kendi scrollback'ini kaydırmaz.
APP_CURSOR_ON = "\x1b[?1h\x1b="
#: Çıkışta normal imleç/keypad moduna dönüş.
APP_CURSOR_OFF = "\x1b[?1l\x1b>"


def install_app_cursor_mode(app: Any) -> None:
    """prompt_toolkit'in tek seferlik `reset_cursor_key_mode` çağrısını, normal
    mod (`?1l`) yerine uygulama modu (`?1h\x1b=`) yayacak şekilde değiştir.

    Tek seferlik olması kritik: her render'da yeniden yaymak Terminal.app'te metin
    bozulmasına yol açıyor (spike geçmişinde doğrulandı).
    """
    app.output.reset_cursor_key_mode = lambda: app.output.write_raw(APP_CURSOR_ON)


def append_text(buffer: Buffer, text: str) -> None:
    """Konuşma tamponuna metin ekle; imleci sona al (takip modu)."""
    new = buffer.text + text
    buffer.set_document(Document(new, cursor_position=len(new)), bypass_readonly=True)


def scroll_lines(buffer: Buffer, delta: int) -> None:
    """İmleci `delta` satır taşı; pencere imleci görünür tutmak için kayar.

    Salt-okunur, odaklı olmayan pencerede `vertical_scroll`'u doğrudan sürmek işe
    yaramaz: imleç sondayken prompt_toolkit her çizimde en alta çeker.
    """
    doc = buffer.document
    row = max(0, min(doc.line_count - 1, doc.cursor_position_row + delta))
    buffer.set_document(
        Document(buffer.text, cursor_position=doc.translate_row_col_to_index(row, 0)),
        bypass_readonly=True,
    )


#: Yukarı/aşağı bir kaydırmada kaç satır (page için katı).
_SCROLL_STEP = 1
_SCROLL_PAGE = 8


class FusionScreen:
    """Tam-ekran kabuk: banner + konuşma + çalışma satırı + giriş kutusu."""

    def __init__(self, banner: str, on_submit: Callable[[str], None]) -> None:
        self._on_submit = on_submit
        self._conversation = TextArea(
            text="",
            read_only=True,
            scrollbar=True,
            focusable=True,
            wrap_lines=True,
        )
        self._work = Window(content=FormattedTextControl(""), height=1)
        self._input = TextArea(height=1, prompt="❯ ", multiline=False, wrap_lines=False)
        self._input.accept_handler = self._handle_submit

        root = HSplit(
            [
                Window(content=FormattedTextControl(banner), height=3),
                Frame(self._conversation, title="konuşma"),
                self._work,
                Frame(self._input, title="mesaj"),
            ]
        )
        self.application: Application[Any] = Application(
            layout=Layout(root, focused_element=self._input),
            key_bindings=self._bindings(),
            full_screen=True,
            mouse_support=False,
        )

    @property
    def conversation_buffer(self) -> Buffer:
        return self._conversation.buffer

    def append(self, text: str) -> None:
        append_text(self._conversation.buffer, text)
        self.application.invalidate()

    def _handle_submit(self, _buff: Buffer) -> bool:
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

        @kb.add("up", eager=True)
        def _up(_e: Any) -> None:
            scroll_lines(self._conversation.buffer, -_SCROLL_STEP)
            self.application.invalidate()

        @kb.add("down", eager=True)
        def _down(_e: Any) -> None:
            scroll_lines(self._conversation.buffer, +_SCROLL_STEP)
            self.application.invalidate()

        @kb.add("pageup", eager=True)
        def _pgup(_e: Any) -> None:
            scroll_lines(self._conversation.buffer, -_SCROLL_PAGE)
            self.application.invalidate()

        @kb.add("pagedown", eager=True)
        def _pgdn(_e: Any) -> None:
            scroll_lines(self._conversation.buffer, +_SCROLL_PAGE)
            self.application.invalidate()

        return kb


def echo_submit(screen: FusionScreen, text: str) -> None:
    """İskelet doğrulaması için basit eko turu. Faz 2'de gerçek motorla değişir."""
    screen.append(f"\n[ben] {text}\n")
    screen.append(f"[eko] {text}\n")

"""Tam-ekran (alternatif ekran) kabuk — doğrulanmış reçeteyle.

Neden alternatif ekran: normal tamponda terminal resize'ı prompt_toolkit'in bayat
imleç modeliyle yaptığı silmeyi ıskalatıp giriş işareti kopyaları biriktiriyordu
ve yukarı kaydırınca eski shell çıktısı görünüyordu. Ekranı uygulama sahiplenince
bu sınıf hatalar ortadan kalkar.

Reçete (gerçek Terminal.app'te ölçülerek doğrulandı):
- full_screen=True (alternatif ekran)
- mouse_support=False (agresif fare takibi resize'ı bozuyor)
- reset_cursor_key_mode → uygulama imleç modu (tekerlek = ok tuşu, scrollback'e kaçmaz)

Konuşma alanı: düz TextArea yerine `AnsiBridge` metnini renkli gösteren
`FormattedTextControl(ANSI(...))` sarılı, salt-okunur, kaydırılabilir bir Window.
Kaydırma imleçle değil `window.vertical_scroll` ile yapılır; temel takip modu ile
kullanıcı en alttaysa yeni içerik alta yapışır, yukarı kaydırdıysa yerinde kalır.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import Frame, TextArea

from .ansi_bridge import AnsiBridge

if TYPE_CHECKING:
    from .state import ReplState

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


def clamp_scroll(vertical_scroll: int, delta: int, max_scroll: int) -> int:
    """Dikey kaydırmayı `[0, max_scroll]` aralığında tutarak `delta` kadar taşı."""
    return max(0, min(max_scroll, vertical_scroll + delta))


#: Yukarı/aşağı bir kaydırmada kaç satır (page için katı).
_SCROLL_STEP = 1
_SCROLL_PAGE = 8


class FusionScreen:
    """Tam-ekran kabuk: banner + konuşma (ANSI) + çalışma satırı + giriş kutusu."""

    def __init__(self, banner: str, on_submit: Callable[[str], None]) -> None:
        self._on_submit = on_submit
        self._bridge = AnsiBridge()
        self._work_text = ""
        # Kullanıcı en alttaysa yeni içerik takip edilir; yukarı kaydırdıysa yerinde kalır.
        self._follow = True

        self._conversation_window = Window(
            content=FormattedTextControl(lambda: ANSI(self._bridge.text)),
            wrap_lines=True,
            always_hide_cursor=True,
            # Greedy yükseklik (min=1, üst sınır yok): pencere içerik yüksekliğine
            # ÇÖKMEMELİ. Çökerse HSplit ekranı doldurmaz, full_screen boyanmayan alt
            # bölgeyi bırakır ve eski terminal içeriği (scrollback) sızar, resize'da
            # giriş satırı kayar. TextArea (Faz 1'in temiz konuşma alanı) tam da bu
            # yüzden height=D(min=1) kullanıyordu.
            height=Dimension(min=1),
        )
        self._work_window = Window(
            content=FormattedTextControl(lambda: ANSI(self._work_text)), height=1
        )
        self._input = TextArea(height=1, prompt="❯ ", multiline=False, wrap_lines=False)
        self._input.accept_handler = self._handle_submit

        root = HSplit(
            [
                Window(content=FormattedTextControl(banner), height=3),
                Frame(self._conversation_window, title="konuşma"),
                self._work_window,
                Frame(self._input, title="mesaj"),
            ]
        )
        self.application: Application[Any] = Application(
            layout=Layout(root, focused_element=self._input),
            key_bindings=self._bindings(),
            full_screen=True,
            # Kanıtlanmış reçete (fullscreen_spike4): mouse_support=False + app-cursor
            # mode (?1h). Terminal.app tekerleği ok tuşuna çevirir; agresif fare takibi
            # yok, resize temiz kalır. Tekerlek up/down bağlamalarını tetikler.
            mouse_support=False,
        )

    @property
    def bridge(self) -> AnsiBridge:
        return self._bridge

    @property
    def conversation_text(self) -> str:
        return self._bridge.text

    @property
    def work_text(self) -> str:
        return self._work_text

    def set_work(self, text: str) -> None:
        self._work_text = text
        self.application.invalidate()

    def clear_work(self) -> None:
        self._work_text = ""
        self.application.invalidate()

    def after_event(self) -> None:
        """Motor olayından sonra: köprüyü drain et, takip modundaysa en alta çek."""
        self._bridge.drain()
        if self._follow:
            self._scroll_to_bottom()
        self.application.invalidate()

    def _scroll_to_bottom(self) -> None:
        info = self._conversation_window.render_info
        if info is None:
            return
        self._conversation_window.vertical_scroll = max(
            0, info.content_height - info.window_height
        )

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

        def _kaydir(delta: int) -> None:
            info = self._conversation_window.render_info
            max_scroll = (
                0 if info is None else max(0, info.content_height - info.window_height)
            )
            self._conversation_window.vertical_scroll = clamp_scroll(
                self._conversation_window.vertical_scroll, delta, max_scroll
            )
            # Kullanıcı en alttan ayrıldıysa takip modunu kapat; alta döndüyse aç.
            self._follow = self._conversation_window.vertical_scroll >= max_scroll
            self.application.invalidate()

        @kb.add("up", eager=True)
        def _up(_e: Any) -> None:
            _kaydir(-_SCROLL_STEP)

        @kb.add("down", eager=True)
        def _down(_e: Any) -> None:
            _kaydir(+_SCROLL_STEP)

        @kb.add("pageup", eager=True)
        def _pgup(_e: Any) -> None:
            _kaydir(-_SCROLL_PAGE)

        @kb.add("pagedown", eager=True)
        def _pgdn(_e: Any) -> None:
            _kaydir(+_SCROLL_PAGE)

        return kb


def echo_submit(screen: FusionScreen, text: str) -> None:
    """İskelet doğrulaması için basit eko turu. Faz 2'de gerçek motorla değişir."""
    screen.bridge.console.print(f"\n[ben] {text}")
    screen.bridge.console.print(f"[eko] {text}")
    screen.after_event()


_DEMO_BANNER = "  ✦ fusion — tam-ekran (deneysel) · çıkış: Ctrl-Q"


async def run_screen_repl(state: ReplState) -> int:
    """Tam-ekran kabuğu gerçek motorla çalıştır (elle doğrulama / deneysel yol).

    Reçete: uygulama imleç modu kurulur; çıkışta normal moda dönülür. Faz 1
    regresyonu: zaten çalışan event loop içinde `run_async()` await edilir.
    """
    import asyncio

    from .screen_turn import run_turn

    screen = FusionScreen(banner=_DEMO_BANNER, on_submit=lambda t: None)

    # Çalışan tur görevlerine referans tut: aksi hâlde GC görevi erkenden
    # toplayıp turu yarıda kesebilir (asyncio zayıf referansla tutar).
    turn_tasks: set[asyncio.Task[None]] = set()

    def _start(text: str) -> None:
        # Turu arka plan görevi yap: giriş kutusu bloklanmasın, çıktı akarken çizilsin.
        task = asyncio.ensure_future(run_turn(text, state, screen))
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

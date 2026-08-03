"""Tam-ekran (alternatif ekran) kabuk — kanıtlanmış reçeteyle (fullscreen_spike4).

Neden alternatif ekran: normal tamponda terminal resize'ı prompt_toolkit'in bayat
imleç modeliyle yaptığı silmeyi ıskalatıp giriş işareti kopyaları biriktiriyordu
ve yukarı kaydırınca eski shell çıktısı görünüyordu. Ekranı uygulama sahiplenince
bu sınıf hatalar ortadan kalkar.

Reçete (fullscreen_spike4'te gerçek Terminal.app'te doğrulandı):
- full_screen=True (alternatif ekran; resize temiz, scrollback izole)
- mouse_support=False (agresif fare takibi resize'ı bozuyor)
- app-cursor mode (?1h): Terminal.app fare tekerleğini ok tuşuna çevirir → tekerlek
  konuşmayı kaydırır ve scrollback'e kaçmaz.
- Kaydırma İMLEÇ-tabanlı: imleç taşınır, pencere imleci görünür tutmak için kayar.
  (`vertical_scroll`'u doğrudan sürmek işe yaramaz: imleç sondayken prompt_toolkit
  her çizimde en alta çeker.)

Konuşma alanı düz metin `TextArea` (renk yok). ANSI renkli içerik (markdown/kod/
diff) için ANSI'yi çözen kaydırılabilir bir kontrol Faz 4'te ayrı spike ile
gelecek — bkz. docs/BACKLOG.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    Float,
    FloatContainer,
    HSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
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


#: Yukarı/aşağı bir kaydırmada kaç satır (page için katı).
_SCROLL_STEP = 1
_SCROLL_PAGE = 8


class FusionScreen:
    """Tam-ekran kabuk: banner + konuşma + çalışma satırı + giriş kutusu."""

    def __init__(
        self,
        banner: str,
        on_submit: Callable[[str], None],
        *,
        on_cancel: Callable[[], None] | None = None,
        on_cycle_mode: Callable[[], str] | None = None,
        on_exit: Callable[[], None] | None = None,
    ) -> None:
        self._on_submit = on_submit
        self._on_cancel = on_cancel or (lambda: None)
        self._on_cycle_mode = on_cycle_mode or (lambda: "")
        self._on_exit = on_exit or (lambda: None)
        self._bridge = AnsiBridge()
        self._work_text = ""
        self._status_text = ""
        self._busy = False
        # Kullanıcı en alttaysa yeni içerik takip edilir; yukarı kaydırdıysa yerinde kalır.
        self._follow = True

        # Modal durumu: aktifken bir Float gösterilir ve motor turu cevabı Future
        # ile bekler. "confirm" (evet/hayır) ya da "text" (serbest metin).
        self._modal_kind: str | None = None
        self._modal_preview = ""
        self._modal_danger: str | None = None
        self._modal_future: asyncio.Future[Any] | None = None

        self._conversation = TextArea(
            text="",
            read_only=True,
            scrollbar=True,
            focusable=True,
            wrap_lines=True,
        )
        self._work_window = Window(content=FormattedTextControl(lambda: self._work_text), height=1)
        self._input = TextArea(height=1, prompt="❯ ", multiline=False, wrap_lines=False)
        self._input.accept_handler = self._handle_submit
        self._modal_input = TextArea(height=1, multiline=False, wrap_lines=False)
        self._modal_input.accept_handler = self._on_text_accept

        root = HSplit(
            [
                Window(content=FormattedTextControl(banner), height=3),
                Window(content=FormattedTextControl(lambda: self._status_text), height=1),
                Frame(self._conversation, title="konuşma"),
                self._work_window,
                Frame(self._input, title="mesaj"),
            ]
        )
        self.application: Application[Any] = Application(
            layout=Layout(
                FloatContainer(
                    content=root,
                    # Sınırlı (bounded) modal kutusu. Konumsuz Float, imleç-tabanlı
                    # yerleştirme yoluna girip konuşmanın kaydırma imleciyle etkileşerek
                    # layout'u bozuyor (resize'da satır kayması + scrollback sızması).
                    # Açık top/left/right vererek bu yolu tamamen atlıyoruz.
                    floats=[Float(self._modal_layer(), top=2, left=6, right=6)],
                ),
                focused_element=self._input,
            ),
            key_bindings=self._bindings(),
            full_screen=True,
            mouse_support=False,
        )

    @property
    def bridge(self) -> AnsiBridge:
        return self._bridge

    @property
    def conversation_text(self) -> str:
        return self._conversation.text

    @property
    def work_text(self) -> str:
        return self._work_text

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def status_text(self) -> str:
        return self._status_text

    def set_status(self, text: str) -> None:
        self._status_text = text
        self.application.invalidate()

    def set_busy(self, value: bool) -> None:
        self._busy = value
        self.application.invalidate()

    def append_text(self, text: str) -> None:
        self._append(text)
        self.application.invalidate()

    def close_modal(self) -> None:
        fut = self._modal_future
        if fut is not None and not fut.done():
            fut.cancel()
        self._modal_kind = None
        self._modal_future = None
        self._focus(self._input)
        self.application.invalidate()

    def request_exit(self) -> None:
        self._on_exit()
        with contextlib.suppress(Exception):
            self.application.exit()

    def set_work(self, text: str) -> None:
        self._work_text = text
        self.application.invalidate()

    def clear_work(self) -> None:
        self._work_text = ""
        self.application.invalidate()

    def after_event(self) -> None:
        """Motor olayından sonra: köprünün yeni metnini konuşmaya ekle."""
        delta = self._bridge.drain()
        if delta:
            self._append(delta)
        self.application.invalidate()

    def _append(self, text: str) -> None:
        """Konuşmaya metin ekle. Takip modundaysa imleç sona alınır (pencere
        alta yapışır); değilse imleç yerinde kalır (kullanıcı yukarıda okuyor)."""
        buf = self._conversation.buffer
        new = buf.text + text
        pos = len(new) if self._follow else buf.cursor_position
        buf.set_document(Document(new, cursor_position=pos), bypass_readonly=True)

    # -- Modal (onay/soru) -------------------------------------------------- #

    def _modal_layer(self) -> ConditionalContainer:
        """Aktif modalı çizen Float içeriği. `_modal_kind`'e göre confirm ya da text."""
        confirm = ConditionalContainer(
            Frame(
                Window(FormattedTextControl(self._confirm_body), wrap_lines=True),
                title="onay",
            ),
            filter=Condition(lambda: self._modal_kind == "confirm"),
        )
        text = ConditionalContainer(
            Frame(
                HSplit(
                    [
                        Window(
                            FormattedTextControl(lambda: self._modal_preview),
                            wrap_lines=True,
                        ),
                        self._modal_input,
                    ]
                ),
                title="soru",
            ),
            filter=Condition(lambda: self._modal_kind == "text"),
        )
        return ConditionalContainer(
            HSplit([confirm, text]),
            filter=Condition(lambda: self._modal_kind is not None),
        )

    def _confirm_body(self) -> str:
        satirlar = [self._modal_preview]
        if self._modal_danger:
            satirlar.append(f"⚠ {self._modal_danger}")
        satirlar.append("Onayla (e) / Reddet (h)")
        return "\n".join(satirlar)

    async def ask_confirm(self, preview: str, danger: str | None = None) -> bool:
        """Onay modalını aç ve kullanıcının e/h yanıtını Future ile bekle."""
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._modal_kind = "confirm"
        self._modal_preview = preview
        self._modal_danger = danger
        self._modal_future = fut
        self.application.invalidate()
        try:
            return await fut
        finally:
            self._modal_kind = None
            self._modal_future = None
            self._focus(self._input)
            self.application.invalidate()

    async def ask_text(self, question: str) -> str:
        """Metin girişli modalı aç ve Enter'da girilen metni Future ile bekle."""
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._modal_kind = "text"
        self._modal_preview = question
        self._modal_danger = None
        self._modal_future = fut
        self._modal_input.text = ""
        self._focus(self._modal_input)
        self.application.invalidate()
        try:
            return await fut
        finally:
            self._modal_kind = None
            self._modal_future = None
            self._focus(self._input)
            self.application.invalidate()

    def _resolve_confirm(self, value: bool) -> None:
        fut = self._modal_future
        if fut is not None and not fut.done():
            fut.set_result(value)

    def _resolve_text(self, value: str) -> None:
        fut = self._modal_future
        if fut is not None and not fut.done():
            fut.set_result(value)

    def _on_text_accept(self, _buff: Buffer) -> bool:
        self._resolve_text(self._modal_input.text)
        return False

    def _focus(self, target: Any) -> None:
        # Çalışan uygulama yoksa (test) odaklama anlamsızdır; sessizce geç.
        with contextlib.suppress(Exception):
            self.application.layout.focus(target)

    def _handle_submit(self, _buff: Buffer) -> bool:
        text = self._input.text.strip()
        self._input.text = ""
        if not text:
            return False
        if self._busy:
            self.append_text("\nAktif istek sürüyor. Ctrl-C ile iptal et.\n")
            return False
        self._on_submit(text)
        return False

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-q")
        def _exit(event: Any) -> None:
            self._on_exit()
            event.app.exit()

        @kb.add("c-c")
        def _cancel(_event: Any) -> None:
            if self._modal_kind == "confirm":
                self._resolve_confirm(False)
            elif self._modal_kind == "text":
                fut = self._modal_future
                if fut is not None and not fut.done():
                    fut.cancel()
            if self._busy or self._modal_kind is not None:
                self._on_cancel()
                self.set_work("iptal ediliyor…")
            else:
                self._input.text = ""

        @kb.add("s-tab", filter=Condition(lambda: self._modal_kind is None), eager=True)
        def _cycle(_event: Any) -> None:
            status = self._on_cycle_mode()
            if status:
                self.set_status(status)

        # Onay modalı açıkken e/h (ve escape) yanıtı Future'a yazar. eager: odaklı
        # giriş kutusu bu tuşları metin olarak yutmadan önce biz yakalarız.
        _confirm_acik = Condition(lambda: self._modal_kind == "confirm")

        @kb.add("e", filter=_confirm_acik, eager=True)
        @kb.add("y", filter=_confirm_acik, eager=True)
        def _confirm_evet(_e: Any) -> None:
            self._resolve_confirm(True)

        @kb.add("h", filter=_confirm_acik, eager=True)
        @kb.add("n", filter=_confirm_acik, eager=True)
        @kb.add("escape", filter=_confirm_acik, eager=True)
        def _confirm_hayir(_e: Any) -> None:
            self._resolve_confirm(False)

        def _scroll(delta: int) -> None:
            # İMLECİ taşı: pencere imleci görünür tutmak için kayar (odaklı olmasa
            # bile). Tekerlek ?1h sayesinde ok tuşu olarak geldiğinden bu yol
            # tekerleği de kapsar.
            buf = self._conversation.buffer
            doc = buf.document
            row = max(0, min(doc.line_count - 1, doc.cursor_position_row + delta))
            buf.set_document(
                Document(buf.text, cursor_position=doc.translate_row_col_to_index(row, 0)),
                bypass_readonly=True,
            )
            # Son satırdaysa takip sürsün; yukarı çıktıysa yerinde kal.
            self._follow = row >= doc.line_count - 1
            self.application.invalidate()

        # Kaydırma yalnızca modal KAPALIYKEN. Modal (özellikle metin girişi) açıkken
        # ok/PageUp giriş kutusunun imlecine gitmeli, arkadaki konuşmayı kaydırmamalı.
        _modal_kapali = Condition(lambda: self._modal_kind is None)

        @kb.add("up", filter=_modal_kapali, eager=True)
        def _up(_e: Any) -> None:
            _scroll(-_SCROLL_STEP)

        @kb.add("down", filter=_modal_kapali, eager=True)
        def _down(_e: Any) -> None:
            _scroll(+_SCROLL_STEP)

        @kb.add("pageup", filter=_modal_kapali, eager=True)
        def _pgup(_e: Any) -> None:
            _scroll(-_SCROLL_PAGE)

        @kb.add("pagedown", filter=_modal_kapali, eager=True)
        def _pgdn(_e: Any) -> None:
            _scroll(+_SCROLL_PAGE)

        return kb


def echo_submit(screen: FusionScreen, text: str) -> None:
    """İskelet doğrulaması için basit eko turu. Gerçek motorla run_turn kullanılır."""
    screen.bridge.console.print(f"\n[ben] {text}")
    screen.bridge.console.print(f"[eko] {text}")
    screen.after_event()


_DEMO_BANNER = "  ✦ fusion — tam-ekran (deneysel) · çıkış: Ctrl-Q"


async def run_screen_repl(state: ReplState) -> int:
    """Tam-ekran görünümü, sahibi belli ve iptal edilebilir tek bir tur göreviyle çalıştır."""
    import os

    if os.environ.get("FUSION_SPIKE") == "1":
        from .screen_spike import run_spike

        return await run_spike(state)

    from .commands import build_registry
    from .screen_turn import run_screen_line, screen_status

    current_task: asyncio.Task[None] | None = None
    registry = build_registry()
    screen: FusionScreen

    def _cancel() -> None:
        nonlocal current_task
        if current_task is not None and not current_task.done():
            current_task.cancel()

    def _cycle() -> str:
        state.cycle_approval()
        return screen_status(state)

    def _exit() -> None:
        _cancel()
        state.running = False

    screen = FusionScreen(
        banner=_DEMO_BANNER,
        on_submit=lambda _text: None,
        on_cancel=_cancel,
        on_cycle_mode=_cycle,
        on_exit=_exit,
    )
    with contextlib.suppress(Exception):
        screen.set_status(screen_status(state))

    def _finished(task: asyncio.Task[None]) -> None:
        nonlocal current_task
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            screen.append_text(f"\nHata: {type(exc).__name__}: {exc}\n")
        finally:
            if current_task is task:
                current_task = None
            screen.set_busy(False)
            screen.clear_work()
            screen.close_modal()
            screen.set_status(screen_status(state))
            screen._focus(screen._input)

    def _start(text: str) -> None:
        nonlocal current_task
        if current_task is not None and not current_task.done():
            screen.append_text("\nAktif istek sürüyor. Ctrl-C ile iptal et.\n")
            return
        screen.set_busy(True)
        current_task = asyncio.create_task(run_screen_line(text, state, screen, registry))
        current_task.add_done_callback(_finished)

    screen._on_submit = _start
    install_app_cursor_mode(screen.application)
    try:
        await screen.application.run_async()
    finally:
        _cancel()
        if current_task is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(current_task, timeout=2.0)
        sys.stdout.write(APP_CURSOR_OFF)
        sys.stdout.flush()
    return 0

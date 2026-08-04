"""Ink-benzeri tek yol REPL çrome'u — `prompt_toolkit` tam-ekran `Application`.

Claude Code modeli: girdi kutusu terminalin EN ALTINA sabit pinlenir, konuşma üstte
kaydırılabilir renkli bir alanda akar. Tam-ekran repaint sayesinde yeniden boyutlandırmada
istem kopyalanmaz (non-fullscreen'in resize hatası çözülür). Çıkışta konuşma gerçek
terminale dökülür; böylece scrollback kaybolmaz.

Renkler fusion kimliğinden gelir: girdi kutusunun üstünde turuncu→pembe gradyan bir çizgi,
`>` istemi ve çalışma satırı aksan renginde. Tuşlar tur boyunca canlı okunur: esc turu
keser, Ctrl-C fusion'dan çıkar, shift-tab mod döndürür, Enter gönderir.

İş mantığı callback'lerle dışarıdadır (test edilebilirlik: TTY olmadan kurulup sınanabilir).
"""

from __future__ import annotations

import asyncio
import io
import shutil
from collections.abc import Callable

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI, HTML, StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea
from rich.console import Console

from ...ui import messages, theme
from ...ui.picker import Choice

#: Girdi kutusunun içindeki istem işareti (Claude Code `> `).
PROMPT = "> "
#: Yapıştırma bu satır/karakter sayısını aşarsa tek satırlık yer tutucuya katlanır.
#: Uzun yapıştırma tek-satır girdiyi şişirir ve gönderilene kadar okunmaz kalır; katlanınca
#: girdi tek satır kalır, tam metin gönderimde geri açılır. (Eski satır-içi modun davranışı.)
FOLD_PASTE_LINES = 10
FOLD_PASTE_CHARS = 600
#: Ok/PageUp ile bir seferde kaç satır kaydırılacağı.
_SCROLL_STEP = 3
_SCROLL_PAGE = 12
#: Alt-chrome'un (gradyan çizgi + çerçeveli girdi + durum) yaklaşık satır yüksekliği;
#: konuşma alanının kaç satır göstereceğini hesaplamak için.
_CHROME_ROWS = 6

#: Onay modunun durum satırındaki rengi — riskli mod göze çarpsın.
_MODE_COLORS = {"auto": theme.OK, "plan": theme.WARN, "security": theme.ERROR}


def format_status(mode: str, engine: str) -> str:
    """Girdinin ALTINDAKİ durum satırının HTML'i: mod + motor + kısayol ipuçları."""
    color = _MODE_COLORS.get(mode, theme.DIM)
    return (
        f"<style fg='{color}'>{theme.ICON_STATUS} {mode}</style>"
        f"<style fg='{theme.DIM}'> · {engine} · {messages.TUI_STATUS_HINT}</style>"
    )


def gradient_rule(width: int) -> StyleAndTextTuples:
    """Girdi kutusunun üstündeki turuncu→pembe gradyanlı yatay çizgi (fusion kimliği)."""
    width = max(1, width)
    fragments: StyleAndTextTuples = []
    for index in range(width):
        ratio = 0.0 if width == 1 else index / (width - 1)
        color = theme.blend(theme.ACCENT, theme.ACCENT_ALT, ratio)
        fragments.append((f"fg:{color}", "─"))
    return fragments


def _style() -> Style:
    """TUI renkleri — fusion aksanı: istem turuncu, girdi kutusu kenarı pembe."""
    return Style.from_dict(
        {
            "frame.border": theme.ACCENT_ALT,
            "prompt": f"{theme.ACCENT} bold",
            "work": theme.ACCENT,
            "choice-title": f"{theme.ACCENT} bold",
            "choice-selected": f"{theme.ACCENT_ALT} bold",
            "choice": theme.DIM,
            "choice-hint": theme.DIM,
        }
    )


class FusionTui:
    """En alta pinli girdi + kaydırılabilir renkli konuşma; tuşları callback'lere yönlendirir."""

    def __init__(
        self,
        *,
        on_submit: Callable[[str], None],
        on_interrupt: Callable[[], None],
        on_exit: Callable[[], None],
        on_cycle_mode: Callable[[], None],
        initial_transcript: str = "",
        on_transcript_change: Callable[[str], None] | None = None,
    ) -> None:
        self._on_submit = on_submit
        self._on_interrupt = on_interrupt
        self._on_exit = on_exit
        self._on_cycle_mode = on_cycle_mode
        self._on_transcript_change = on_transcript_change
        self._work_text = ""
        self._status_html = ""
        self._status_mode = "auto"
        self._status_engine = "agent"
        self._mode = "idle"
        self._answer: asyncio.Future[object] | None = None
        # Uygulama-içi seçim modalı durumu (nested picker YOK): /mode, /level, /effort.
        self._choices: list[Choice] = []
        self._choice_index = 0
        self._choice_title = ""
        # Katlanmış yapıştırmaların yer tutucu → tam metin eşlemesi; her gönderimde temizlenir.
        self._pastes: dict[str, str] = {}
        self._paste_seq = 0

        # Konuşma tamponu: renderer bu Rich console'a RENKLİ yazar; ANSI olarak gösterilir.
        self._sink = io.StringIO()
        if initial_transcript:
            self._sink.write(initial_transcript.rstrip("\n") + "\n")
        self._console = Console(
            file=self._sink, force_terminal=True, color_system="truecolor", width=_term_width()
        )
        self._conversation = self._sink.getvalue()
        # Kaydırma ofseti: 0 = en altta (takip). Yukarı kaydırınca artar.
        self._scroll = 0
        self._unread_lines = 0

        self._input = TextArea(
            height=1,
            multiline=False,
            wrap_lines=False,
            prompt=[("class:prompt", PROMPT)],
            accept_handler=self._accept,
        )
        conversation = Window(
            FormattedTextControl(self._conversation_fragments),
            wrap_lines=True,
            always_hide_cursor=True,
        )
        work_window = ConditionalContainer(
            Window(FormattedTextControl(lambda: self._work_text), height=1, style="class:work"),
            filter=Condition(lambda: bool(self._work_text)),
        )
        rule = Window(FormattedTextControl(self._rule_fragments), height=1)
        status_window = Window(FormattedTextControl(lambda: HTML(self._status_html)), height=1)
        # Seçim modalı: yalnızca "choice" modunda, girdinin hemen üstünde ok-tuşlu liste.
        choice_window = ConditionalContainer(
            Window(FormattedTextControl(self._choice_fragments)),
            filter=Condition(lambda: self._mode == "choice"),
        )
        # Konuşma alanı tüm boşluğu kaplar; alt-chrome (çizgi + girdi + durum) en altta pinli.
        root = HSplit(
            [conversation, work_window, choice_window, rule, Frame(self._input), status_window],
            height=Dimension(),
        )
        self.application: Application[None] = Application(
            layout=Layout(root, focused_element=self._input),
            key_bindings=self._bindings(),
            style=_style(),
            full_screen=True,
            mouse_support=True,
        )

    @property
    def console(self) -> Console:
        """Renderer'ın RENKLİ yazacağı Rich console (konuşma tamponuna bağlı)."""
        return self._console

    # -- Dışarıdan beslenen durum ------------------------------------------- #

    def sync_conversation(self) -> None:
        """Yeni çıktıyı aktar; kullanıcı geçmişe bakıyorsa konumunu koru."""
        previous_lines = len(self._conversation.splitlines())
        updated = self._sink.getvalue()
        updated_lines = len(updated.splitlines())
        added = max(0, updated_lines - previous_lines)
        self._conversation = updated
        if self._scroll > 0 and added:
            # Alttan ofseti büyütmek, kullanıcının baktığı eski satırları sabit tutar.
            self._scroll += added
            self._unread_lines += added
        elif self._scroll == 0:
            self._unread_lines = 0
        if self._on_transcript_change is not None:
            self._on_transcript_change(self._conversation)
        self._refresh_status()

    def set_work(self, text: str) -> None:
        self._work_text = text
        self._invalidate()

    def clear_work(self) -> None:
        self._work_text = ""
        self._invalidate()

    def set_status(self, mode: str, engine: str) -> None:
        self._status_mode = mode
        self._status_engine = engine
        self._refresh_status()

    def _refresh_status(self) -> None:
        self._status_html = format_status(self._status_mode, self._status_engine)
        if self._scroll > 0 and self._unread_lines:
            self._status_html += (
                f"<style fg='{theme.ACCENT_ALT}'> · ↓ {self._unread_lines} yeni satır</style>"
            )
        self._invalidate()

    def request_exit(self) -> None:
        if self.application.is_running:
            self.application.exit()

    @property
    def transcript(self) -> str:
        """Oturum boyunca birikmiş renkli konuşma metni (çıkışta scrollback'e dökmek için)."""
        return self._sink.getvalue()

    # -- Modal (onay/soru) -------------------------------------------------- #

    async def await_confirm(self) -> bool:
        return bool(await self._await_answer("confirm"))

    async def await_text(self) -> str:
        return str(await self._await_answer("ask"))

    async def await_choice(self, title: str, choices: list[Choice]) -> str | None:
        """Uygulama-içi ok-tuşlu seçim (nested picker YOK). Seçilen değeri, esc'te None."""
        if not choices:
            return None
        self._choices = list(choices)
        self._choice_index = 0
        self._choice_title = title
        result = await self._await_answer("choice")
        return None if result is None else str(result)

    async def _await_answer(self, mode: str) -> object:
        future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        self._answer = future
        self._mode = mode
        self._invalidate()
        try:
            return await future
        finally:
            self._mode = "idle"
            self._answer = None
            self._invalidate()

    def _resolve(self, value: object) -> None:
        future = self._answer
        if future is not None and not future.done():
            future.set_result(value)

    # -- Konuşma render'ı --------------------------------------------------- #

    def _conversation_fragments(self) -> ANSI:
        """Konuşmanın görünür kısmı: kaydırma ofsetine göre son satırlar, ANSI renkli."""
        lines = self._conversation.splitlines()
        body = max(1, _term_rows() - _CHROME_ROWS)
        end = max(0, len(lines) - self._scroll)
        start = max(0, end - body)
        return ANSI("\n".join(lines[start:end]))

    def _rule_fragments(self) -> StyleAndTextTuples:
        return gradient_rule(_term_width())

    def _choice_fragments(self) -> StyleAndTextTuples:
        """Seçim modalının satırları: başlık + seçenekler, seçili olan işaretli."""
        fragments: StyleAndTextTuples = [("class:choice-title", f" {self._choice_title}\n")]
        for index, choice in enumerate(self._choices):
            selected = index == self._choice_index
            marker = theme.ICON_STATUS if selected else " "
            style = "class:choice-selected" if selected else "class:choice"
            fragments.append((style, f" {marker} {choice.label}"))
            if choice.description:
                fragments.append(("class:choice-hint", f"   {choice.description}"))
            fragments.append(("", "\n"))
        return fragments

    def _move_choice(self, delta: int) -> None:
        if self._choices:
            self._choice_index = (self._choice_index + delta) % len(self._choices)
            self._invalidate()

    # -- Tuş yönlendirmesi -------------------------------------------------- #

    def _accept(self, buffer: object) -> bool:
        text = self._expand_pastes(getattr(buffer, "text", ""))
        self._pastes.clear()  # yer tutucular yalnızca içinde bulunulan satır boyunca geçerli
        if self._mode == "ask":
            self._resolve(text)
        elif self._mode == "choice":
            self._resolve(self._choices[self._choice_index].value)
        else:
            self._on_submit(text)
        return False

    def _fold_paste(self, text: str) -> None:
        """Yapıştırmayı girdiye koy; uzunsa tam metni sakla ve tek satırlık yer tutucu bırak."""
        line_count = text.count("\n") + 1
        long_enough = line_count > FOLD_PASTE_LINES or len(text) > FOLD_PASTE_CHARS
        buffer = self._input.buffer
        if not long_enough:
            buffer.insert_text(text)
            return
        self._paste_seq += 1
        if line_count > 1:
            token = messages.REPL_PASTE_FOLDED.format(count=line_count, index=self._paste_seq)
        else:
            token = messages.REPL_PASTE_FOLDED_CHARS.format(count=len(text), index=self._paste_seq)
        self._pastes[token] = text
        buffer.insert_text(token)

    def _expand_pastes(self, line: str) -> str:
        """Satırdaki yer tutucuları sakladıkları tam metinle değiştir."""
        for token, text in self._pastes.items():
            line = line.replace(token, text)
        return line

    def _scroll_by(self, delta: int) -> None:
        lines = len(self._conversation.splitlines())
        body = max(1, _term_rows() - _CHROME_ROWS)
        maximum = max(0, lines - body)
        self._scroll = max(0, min(maximum, self._scroll + delta))
        if self._scroll == 0:
            self._unread_lines = 0
        self._refresh_status()

    def _scroll_home(self) -> None:
        lines = len(self._conversation.splitlines())
        body = max(1, _term_rows() - _CHROME_ROWS)
        self._scroll = max(0, lines - body)
        self._refresh_status()

    def _scroll_end(self) -> None:
        self._scroll = 0
        self._unread_lines = 0
        self._refresh_status()

    def _bindings(self) -> KeyBindings:
        from prompt_toolkit.keys import Keys

        kb = KeyBindings()
        confirm = Condition(lambda: self._mode == "confirm")
        idle = Condition(lambda: self._mode == "idle")

        @kb.add(Keys.BracketedPaste)
        def _paste(event: object) -> None:
            # Uzun/çok-satırlı yapıştırma girdiye AKMAZ: katlanıp yer tutucuya iner,
            # tam metin gönderimde geri açılır. Tek-satır girdi kısa kalır.
            self._fold_paste(getattr(event, "data", ""))

        @kb.add("c-q")
        @kb.add("c-c")
        def _exit(_event: object) -> None:
            # Kullanıcı isteği: Ctrl-C fusion'dan ÇIKAR (turu kesmek için esc var).
            self._on_exit()

        @kb.add("escape", eager=True)
        def _interrupt(_event: object) -> None:
            self._cancel_or_interrupt()

        @kb.add("s-tab")
        def _cycle(_event: object) -> None:
            self._on_cycle_mode()

        @kb.add("e", filter=confirm, eager=True)
        @kb.add("y", filter=confirm, eager=True)
        def _yes(_event: object) -> None:
            self._resolve(True)

        @kb.add("h", filter=confirm, eager=True)
        @kb.add("n", filter=confirm, eager=True)
        def _no(_event: object) -> None:
            self._resolve(False)

        # Oklar: seçim modunda seçeneği gezer, boştayken konuşmayı kaydırır.
        nav = Condition(lambda: self._mode in ("idle", "choice"))

        @kb.add("up", filter=nav, eager=True)
        def _up(_event: object) -> None:
            self._move_choice(-1) if self._mode == "choice" else self._scroll_by(_SCROLL_STEP)

        @kb.add("down", filter=nav, eager=True)
        def _down(_event: object) -> None:
            self._move_choice(1) if self._mode == "choice" else self._scroll_by(-_SCROLL_STEP)

        @kb.add("pageup", filter=idle, eager=True)
        def _pgup(_event: object) -> None:
            self._scroll_by(_SCROLL_PAGE)

        @kb.add("pagedown", filter=idle, eager=True)
        def _pgdn(_event: object) -> None:
            self._scroll_by(-_SCROLL_PAGE)

        @kb.add(Keys.ScrollUp, filter=idle, eager=True)
        def _mouse_up(_event: object) -> None:
            self._scroll_by(_SCROLL_STEP)

        @kb.add(Keys.ScrollDown, filter=idle, eager=True)
        def _mouse_down(_event: object) -> None:
            self._scroll_by(-_SCROLL_STEP)

        @kb.add("home", filter=idle, eager=True)
        @kb.add("c-home", filter=idle, eager=True)
        def _home(_event: object) -> None:
            self._scroll_home()

        @kb.add("end", filter=idle, eager=True)
        @kb.add("c-end", filter=idle, eager=True)
        def _end(_event: object) -> None:
            self._scroll_end()

        @kb.add("c-r", filter=idle, eager=True)
        def _history(_event: object) -> None:
            # Ctrl-R: en eski transcript noktasına hızlı geçiş; End ile canlı akışa dönülür.
            self._scroll_home()

        return kb

    def _cancel_or_interrupt(self) -> None:
        if self._mode == "confirm":
            self._resolve(False)
        elif self._mode == "ask":
            self._resolve("")
        elif self._mode == "choice":
            self._resolve(None)
        else:
            self._on_interrupt()

    def _invalidate(self) -> None:
        if self.application.is_running:
            self.application.invalidate()


def _term_width() -> int:
    return max(20, shutil.get_terminal_size((100, 40)).columns)


def _term_rows() -> int:
    return max(10, shutil.get_terminal_size((100, 40)).lines)

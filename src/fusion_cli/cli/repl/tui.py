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
import logging
import shutil
import time
from collections.abc import Callable
from html import escape as html_escape

from prompt_toolkit.application import Application
from prompt_toolkit.completion import Completer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, Filter
from prompt_toolkit.formatted_text import ANSI, HTML, StyleAndTextTuples
from prompt_toolkit.history import History
from prompt_toolkit.key_binding import DynamicKeyBindings, KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, SearchToolbar, TextArea
from rich.console import Console

from ...config.keybindings import COMMAND_PREFIX, CONTEXT_TUI, KeyMap, load_keymap
from ...ui import messages, theme
from ...ui.picker import Choice, initial_index
from . import input_actions, vim_remaps
from .choice_search import ChoiceSearch
from .input import FOLD_PASTE_CHARS, FOLD_PASTE_LINES
from .status_line_runner import ansi_for_tui
from .tui_input_keys import (
    DOUBLE_PRESS_SECONDS,
    MAX_INPUT_ROWS,
    DoublePress,
    register_shift_enter,
    submit_or_newline,
)

_logger = logging.getLogger(__name__)

#: İki Esc'in "çift basış" sayılacağı en uzun aralık (saniye).
DOUBLE_ESCAPE_SECONDS = 0.6

#: Girdi kutusunun içindeki istem işareti (Claude Code `> `).
PROMPT = "> "
#: Ok/PageUp ile bir seferde kaç satır kaydırılacağı.
_SCROLL_STEP = 3
_SCROLL_PAGE = 12
#: Seçicide numara tuşuyla seçilebilen ilk seçenekler (Claude Code Select, 1-9).
_NUMBERED_CHOICES = 9
#: Çalışma satırının dönen karesi. Braille noktaları tek hücre genişliğindedir;
#: monospace hizayı bozmaz ve kare değişince satır kaymaz.
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
#: Kare süresi. 80 ms göze akıcı gelen en UZUN aralıktır; daha kısası tam-ekran
#: repaint maliyetini karşılıksız artırır.
SPINNER_INTERVAL_S = 0.08
#: Tekerleği terminalin KENDİ scrollback'ini kaydırmaktan alıkoyan kip dizileri.
#:
#: Alternatif ekrandayken macOS Terminal.app tekerleği ANA tampona uygular:
#: kullanıcı yukarı kaydırınca fusion'ın konuşmasını değil, fusion'dan ÖNCEKİ
#: terminal çıktısını görür. `\e[3J` ile scrollback'i temizleme denemesi bu
#: terminalde işe yaramaz — Terminal.app ED 3'ü desteklemez (iTerm2 destekler).
#:
#: `?1007h` xterm'in "alternate scroll" kipidir: alternatif ekranda tekerlek
#: kaydırmak yerine ok tuşu üretir. `?1h` (DECCKM) Terminal.app'in aynı davranışı
#: uyguladığı kiptir; ok tuşlarının kodlaması `ESC [ A` yerine `ESC O A` olur ve
#: prompt_toolkit ikisini de çözer. Desteklenmeyen kipi terminal sessizce yok sayar.
_WHEEL_AS_ARROWS_ON = "\x1b[?1007h\x1b[?1h"
_WHEEL_AS_ARROWS_OFF = "\x1b[?1007l\x1b[?1l"

#: Alt-chrome'un (gradyan çizgi + çerçeveli girdi + durum) yaklaşık satır yüksekliği;
#: konuşma alanının kaç satır göstereceğini hesaplamak için.
_CHROME_ROWS = 6


def format_status(
    mode: str, engine: str, context: str = "", custom: str = "", *, vim: bool = False
) -> str:
    """Girdinin ALTINDAKİ durum satırının HTML'i: mod + motor + bağlam sayacı + ipuçları.

    `context` bağlam sayacıdır (`status_view.context_label`, P-027); boşsa yazılmaz.
    `custom` kullanıcı betiğinin ürettiği satırdır (P-069): doluysa sayacın yerine geçer.
    `vim` açıkken kısa `vim` etiketi eklenir (P-067).
    """
    color = theme.MODE_COLORS.get(mode, theme.DIM)
    # Çok satırlı/ANSI betik çıktısı (#192) TUI'de kendi satırlarında gösterilir
    # (`custom_status_window`); burada yalnız tek satır olanı yerine geçer.
    shown = (
        html_escape(custom) if custom and "\n" not in custom and "\x1b" not in custom else context
    )
    extra = f" · {shown}" if shown else ""
    if vim:
        extra += " · vim"
    return (
        f"<style fg='{color}'>{theme.ICON_STATUS} {mode}</style>"
        f"<style fg='{theme.DIM}'> · {engine}{extra} · {messages.TUI_STATUS_HINT}</style>"
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
        completer: Completer | None = None,
        keymap: KeyMap | None = None,
        on_rewind: Callable[[], None] | None = None,
        on_background: Callable[[], None] | None = None,
        history: History | None = None,
        is_busy: Callable[[], bool] | None = None,
    ) -> None:
        self._on_submit = on_submit
        self._on_interrupt = on_interrupt
        self._on_exit = on_exit
        self._on_cycle_mode = on_cycle_mode
        self._on_transcript_change = on_transcript_change
        self._on_rewind = on_rewind
        self._on_background = on_background
        #: Tur sürüyor mu? Ctrl+C keser; boştayken temizler/çıkar (#195).
        self._is_busy = is_busy or (lambda: self._work_source is not None)
        self._ctrl_c = DoublePress()
        self._ctrl_d = DoublePress()
        #: Durum satırında geçici ipucu ("çıkmak için tekrar Ctrl+C").
        self._flash = ""
        #: Boş girdide son Esc'in zamanı; ikincisi bu pencere içinde gelirse `/rewind` açılır.
        self._last_escape_at = 0.0
        #: Dolu girdide son Esc'in zamanı; ikincisi girdiyi temizler (#222).
        self._last_clear_escape_at = 0.0
        # Metin DEĞİL, metni üreten şey tutulur: çalışma satırındaki süre her
        # karede yeniden hesaplanmalı (bkz. work_line.WorkLineSink.render).
        self._work_source: Callable[[], str] | None = None
        self._spinner_frame = 0
        self._spinner_task: asyncio.Task[None] | None = None
        self._wheel_modes_on = False
        self._status_html = ""
        self._status_mode = "auto"
        self._status_engine = "agent"
        self._status_context = ""
        self._status_custom = ""
        self._status_vim = False
        #: Ctrl+S taslağı (#216) ve kuyruk kancaları (#190: Up ile geri alma, chat:sendNow).
        self._stash = input_actions.PromptStash()
        self._take_back: Callable[[], list[str]] | None = None
        self._send_now: Callable[[str], None] | None = None
        #: `vimInsertModeRemaps` dizileri (#217); `set_vim_remaps` ile verilir.
        self._vim_remaps: tuple[str, ...] = ()
        #: Tuş tablosu (P-067); `rebind` dosya değişince yeniler.
        self._keymap = keymap or load_keymap()
        self._kb = self._bindings()
        self._mode = "idle"
        self._answer: asyncio.Future[object] | None = None
        #: Tek cevap yuvası: modallar SIRAYLA açılır (#209). Ölçüldü (1 Kasım): tur
        #: sürerken açılan `/model` seçicisi ile araç onayı aynı yuvayı eziyor, Enter
        #: yanlış soruyu yanıtlıyor ve ilk seçici hiç çözülmüyordu.
        self._modal_lock = asyncio.Lock()
        # Uygulama-içi seçim modalı durumu (nested picker YOK): /mode, /level, /effort.
        self._choices: list[Choice] = []
        self._choice_index = 0
        self._choice_title = ""
        # Enter yerine `<tuş>:<değer>` döndüren seçim tuşları (#231 `/copy` seçicisinde `w`).
        self._choice_alt_keys: tuple[str, ...] = ()
        #: Son seçim numara tuşuyla mı yapıldı (Claude Code: özet seçeneği talimatsız, #199).
        self.picked_by_number = False
        # Yazarak arama (#202): yalnız `searchable=True` seçicilerde (oturum seçicisi).
        self._choice_search: ChoiceSearch | None = None
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

        # Çok satırlı girdi (#197), dizin başına geçmiş ve Ctrl+R araması (#196).
        register_shift_enter()
        self._search = SearchToolbar()
        self._input = TextArea(
            height=Dimension(min=1, max=MAX_INPUT_ROWS),
            dont_extend_height=True,
            multiline=True,
            wrap_lines=True,
            prompt=[("class:prompt", PROMPT)],
            accept_handler=self._accept,
            # Tab ile `/komut` ve `@yol` tamamlama (P-022); yazarken menü açılmaz.
            completer=completer,
            complete_while_typing=False,
            history=history,
            search_field=self._search,
        )
        conversation = Window(
            FormattedTextControl(self._conversation_fragments),
            wrap_lines=True,
            always_hide_cursor=True,
        )
        work_window = ConditionalContainer(
            Window(FormattedTextControl(self._work_fragments), height=1, style="class:work"),
            filter=Condition(lambda: bool(self._work_now())),
        )
        rule = Window(FormattedTextControl(self._rule_fragments), height=1)
        status_window = Window(FormattedTextControl(lambda: HTML(self._status_html)), height=1)
        # Claude Code: betik çıktısı yerleşik çubuğun ÜSTÜNDE kendi satır(lar)ında, ANSI renk
        # ve OSC 8 bağlantılarıyla (#192). Tek satırlık düz çıktı eski yerinde kalır.
        custom_window = ConditionalContainer(
            Window(
                FormattedTextControl(lambda: ANSI(ansi_for_tui(self._status_custom))),
                height=lambda: Dimension.exact(self._status_custom.count("\n") + 1),
            ),
            filter=Condition(self._custom_is_rich),
        )
        # Seçim modalı: yalnızca "choice" modunda, girdinin hemen üstünde ok-tuşlu liste.
        choice_window = ConditionalContainer(
            Window(FormattedTextControl(self._choice_fragments)),
            filter=Condition(lambda: self._mode == "choice"),
        )
        # Konuşma alanı tüm boşluğu kaplar; alt-chrome (çizgi + girdi + durum) en altta pinli.
        root = HSplit(
            [
                conversation,
                work_window,
                choice_window,
                rule,
                Frame(self._input),
                self._search,
                custom_window,
                status_window,
            ],
            height=Dimension(),
        )
        self.application: Application[None] = Application(
            layout=Layout(root, focused_element=self._input),
            # Bağlar tablodan üretilir; `DynamicKeyBindings` her tuşta güncel tabloyu okur.
            key_bindings=DynamicKeyBindings(lambda: self._kb),
            style=_style(),
            full_screen=True,
            # Fare izleme KAPALI. Açıkken prompt_toolkit terminale
            # `?1000h/?1003h/?1006h/?1015h` yazıyor ve tüm fare olaylarını kendine
            # alıyordu; bu, terminalin KENDİ metin seçimini öldürüyor — kullanıcı
            # ekrandaki hiçbir şeyi fareyle seçip kopyalayamıyordu (ölçüldü, pty).
            # Karşılığında tekerlekle kaydırma gider; kaydırma klavyeden yapılır
            # (yukarı/aşağı, PageUp/PageDown, Home/End). Kopyalayabilmek,
            # tekerlekle kaydırmaktan daha temel bir beklentidir.
            mouse_support=False,
        )
        # Kipler ilk render'dan SONRA kurulmalı (gerekçe `_apply_wheel_modes`'ta).
        self.application.after_render += self._apply_wheel_modes

    # -- Terminal kipleri --------------------------------------------------- #

    def _apply_wheel_modes(self, _sender: object = None) -> None:
        """Tekerleği uygulamaya yönlendiren kipleri yaz — ilk render'dan SONRA bir kez.

        prompt_toolkit açılışta `?1l` yazıyor; kip ondan önce kurulursa geri
        alınır. Bu yüzden `after_render` kancasına bağlıdır.
        """
        if self._wheel_modes_on:
            return
        self._wheel_modes_on = True
        self._write_raw(_WHEEL_AS_ARROWS_ON)

    def restore_wheel_modes(self) -> None:
        """Çıkışta kipleri geri al: terminal fusion'dan sonra normal davranmalı."""
        if not self._wheel_modes_on:
            return
        self._wheel_modes_on = False
        self._write_raw(_WHEEL_AS_ARROWS_OFF)

    def _write_raw(self, data: str) -> None:
        output = self.application.output
        output.write_raw(data)
        output.flush()

    @property
    def console(self) -> Console:
        """Renderer'ın RENKLİ yazacağı Rich console (konuşma tamponuna bağlı)."""
        return self._console

    # -- Dışarıdan beslenen durum ------------------------------------------- #

    def sync_conversation(self) -> None:
        """Yeni çıktıyı aktar; kullanıcı geçmişe bakıyorsa konumunu koru."""
        # Terminal yeniden boyutlandıysa Rich console genişliği de güncellenir: kuruluşta bir
        # kez hesaplanıyordu ve tablolar/kutular/kurallar eski genişlikte kalıyordu (L2-22).
        self._console.width = _term_width()
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

    def _work_now(self) -> str:
        """Çalışma satırının O ANKİ metni."""
        return "" if self._work_source is None else self._work_source()

    def _work_fragments(self) -> StyleAndTextTuples:
        """Çalışma satırı: dönen kare + kaynağın o anda ürettiği metin."""
        text = self._work_now()
        if not text:
            return []
        frame = SPINNER_FRAMES[self._spinner_frame % len(SPINNER_FRAMES)]
        return [("class:work", f" {frame}{text}")]

    def set_work_source(self, source: Callable[[], str]) -> None:
        """Çalışma satırını besleyecek kaynağı bağla.

        Sabit metin için `lambda: "…"` verilir; tek mekanizma, iki kullanım.
        """
        self._work_source = source
        self._start_spinner()
        self._invalidate()

    @property
    def work_source(self) -> Callable[[], str] | None:
        """Modal geçici bir metin gösterirken geri yüklenecek çalışma kaynağı."""
        return self._work_source

    def clear_work(self) -> None:
        self._work_source = None
        self._stop_spinner()
        self._invalidate()

    # -- Spinner ------------------------------------------------------------ #
    # Çalışma satırı YALNIZCA model olaylarıyla güncelleniyordu; iki olay arasında
    # dakikalarca kıpırdamıyor ve "dondu" gibi görünüyordu. Dönen kare, olay
    # gelmese bile turun sürdüğünü gösterir.

    def _start_spinner(self) -> None:
        if self._spinner_task is not None and not self._spinner_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Olay döngüsü yok (test ya da TTY dışı kurulum): animasyon atlanır,
            # çalışma satırı yine olaylarla güncellenir.
            return
        self._spinner_task = loop.create_task(self._spin())
        self._spinner_task.add_done_callback(_log_spinner_result)

    def _stop_spinner(self) -> None:
        task, self._spinner_task = self._spinner_task, None
        if task is not None and not task.done():
            task.cancel()

    async def _spin(self) -> None:
        """Çalışma satırı durana kadar kareyi ilerlet ve ekranı tazele."""
        while self._work_source is not None:
            await asyncio.sleep(SPINNER_INTERVAL_S)
            self._spinner_frame += 1
            self._invalidate()

    def set_status(
        self, mode: str, engine: str, context: str = "", custom: str = "", *, vim: bool = False
    ) -> None:
        self._status_mode = mode
        self._status_engine = engine
        self._status_context = context
        self._status_custom = custom
        self._status_vim = vim
        self._refresh_status()

    def _custom_is_rich(self) -> bool:
        custom = self._status_custom
        return bool(custom) and ("\n" in custom or "\x1b" in custom)

    def set_vim(self, enabled: bool) -> None:
        """Vim düzenleme kipini aç/kapa (P-067); durum satırı etiketi `set_status` ile gelir."""
        from prompt_toolkit.enums import EditingMode

        self.application.editing_mode = EditingMode.VI if enabled else EditingMode.EMACS

    def set_vim_remaps(self, remaps: tuple[str, ...]) -> None:
        """`vimInsertModeRemaps` dizilerini uygula (bağlar yeniden kurulur)."""
        if remaps != self._vim_remaps:
            self._vim_remaps = remaps
            self.rebind(self._keymap)

    def vim_mode_name(self) -> str:
        """Durum satırı JSON'u için `INSERT` / `NORMAL` / `VISUAL` (#217)."""
        from prompt_toolkit.key_binding.vi_state import InputMode

        state = self.application.vi_state
        if getattr(state, "input_mode", None) == InputMode.NAVIGATION:
            return "NORMAL"
        selection = self._input.buffer.selection_state
        return "VISUAL" if selection is not None else "INSERT"

    @property
    def keymap(self) -> KeyMap:
        return self._keymap

    def rebind(self, keymap: KeyMap) -> None:
        """Tuş tablosunu yenile (dosya değişti); çalışan uygulama yeniden kurulmaz."""
        self._keymap = keymap
        self._kb = self._bindings()
        self._invalidate()

    def _refresh_status(self) -> None:
        self._status_html = format_status(
            self._status_mode,
            self._status_engine,
            self._status_context,
            self._status_custom,
            vim=self._status_vim,
        )
        if self._flash:
            self._status_html += f"<style fg='{theme.WARN}'> · {html_escape(self._flash)}</style>"
        if self._scroll > 0 and self._unread_lines:
            self._status_html += (
                f"<style fg='{theme.ACCENT_ALT}'> · ↓ {self._unread_lines} yeni satır</style>"
            )
        self._invalidate()

    def refresh_style(self) -> None:
        """`/theme` sonrası renkleri yeniden kur (P-070): stil ve durum satırı yeniden üretilir."""
        self.application.style = _style()
        self._refresh_status()

    def scroll_to_match(self, text: str) -> int:
        """Konuşmada `text` geçen son satıra kaydır; eşleşen satır sayısını döndür (P-070)."""
        needle = text.casefold()
        lines = self._conversation.splitlines()
        matches = [index for index, line in enumerate(lines) if needle in line.casefold()]
        if not matches:
            return 0
        # Eşleşen satır görünür alanın ALT kenarına gelir: altında kalan satırlar gizlenir.
        self._scroll = max(0, len(lines) - matches[-1] - 1)
        self._refresh_status()
        return len(matches)

    def request_exit(self) -> None:
        self._stop_spinner()
        if self.application.is_running:
            self.application.exit()

    def set_input(self, text: str) -> None:
        """Giriş kutusunu metinle doldur, imleç sonda (`/voice` dikte metni, P-072)."""
        self._input.buffer.set_document(Document(text, len(text)), bypass_readonly=True)
        self._invalidate()

    @property
    def transcript(self) -> str:
        """Oturum boyunca birikmiş renkli konuşma metni (çıkışta scrollback'e dökmek için)."""
        return self._sink.getvalue()

    # -- Modal (onay/soru) -------------------------------------------------- #

    async def await_text(self) -> str:
        async with self._modal_lock:
            return str(await self._await_answer("ask"))

    async def await_choice(
        self,
        title: str,
        choices: list[Choice],
        *,
        alt_keys: tuple[str, ...] = (),
        searchable: bool = False,
        initial: str = "",
    ) -> str | None:
        """Uygulama-içi ok-tuşlu seçim (nested picker YOK). Seçilen değeri, esc'te None.

        `alt_keys` tuşları Enter yerine `<tuş>:<değer>` döndürür (`/copy` seçicisinde `w`,
        `/model` seçicisinde `s`/`left`/`right`). `initial` imlecin başladığı değerdir.
        """
        if not choices:
            return None
        async with self._modal_lock:
            return await self._run_choice(title, choices, alt_keys, searchable, initial)

    async def _run_choice(
        self,
        title: str,
        choices: list[Choice],
        alt_keys: tuple[str, ...],
        searchable: bool,
        initial: str = "",
    ) -> str | None:
        self._choices = list(choices)
        self._choice_index = initial_index(self._choices, initial)
        self._choice_title = title
        self._choice_alt_keys = alt_keys
        self._choice_search = ChoiceSearch(choices) if searchable else None
        self.picked_by_number = False
        try:
            result = await self._await_answer("choice")
        finally:
            self._choice_alt_keys = ()
            self._choice_search = None
        return None if result is None else str(result)

    def _choice_type(self, char: str) -> bool:
        """Aranabilir seçicide karakteri sorguya işle; liste süzülür (#202)."""
        search = self._choice_search
        if search is None or not search.type(char):
            return False
        self._apply_search(search)
        return True

    def _apply_search(self, search: ChoiceSearch) -> None:
        self._choices = search.visible()
        self._choice_index = 0
        self._invalidate()

    def _searching(self) -> bool:
        return self._choice_search is not None and self._choice_search.active

    def _pick_number(self, char: str) -> None:
        """Claude Code Select: 1-9 numaralı seçeneği hemen seç (aranabilir seçicide değil)."""
        if self._choice_search is not None or not char.isdigit() or char == "0":
            return
        position = int(char) - 1
        if position < len(self._choices):
            self.picked_by_number = True
            self._resolve(self._choices[position].value)

    def _pick_alt(self, key: str) -> None:
        """Seçim kipinde ek tuş: imlecin üzerindeki seçeneği `<tuş>:<değer>` olarak döndür."""
        if self._choices and key in self._choice_alt_keys:
            self._resolve(f"{key}:{self._choices[self._choice_index].value}")

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
        if self._choice_search is not None and self._choice_search.active:
            search_line = messages.CHOICE_SEARCH.format(query=self._choice_search.query or "")
            fragments.append(("class:choice-hint", f" {search_line}\n"))
        for index, choice in enumerate(self._choices):
            selected = index == self._choice_index
            marker = theme.ICON_STATUS if selected else " "
            style = "class:choice-selected" if selected else "class:choice"
            number = f"{index + 1}. " if index < _NUMBERED_CHOICES else "   "
            fragments.append((style, f" {marker} {number}{choice.label}"))
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
            self._pick_current()
        else:
            self._on_submit(text)
        return False

    def _pick_current(self) -> None:
        """Seçim kipinde imlecin üzerindeki seçeneği uygula.

        Ayrı bir metot: Enter'ı hem girdi tamponunun accept işleyicisi hem de
        `choice` kipine bağlı açık tuş bağlaması çağırır. İkisinin AYNI kararı
        vermesi gerekir; kopyalanmış iki gövde kaçınılmaz olarak ayrışırdı.
        """
        if self._choices:
            self._resolve(self._choices[self._choice_index].value)

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
        """Tuş bağları: yapısal olanlar sabit, eylemler tablodan (P-067)."""
        from prompt_toolkit.keys import Keys

        kb = KeyBindings()
        idle = Condition(lambda: self._mode == "idle")
        # Kaydırma SORU SORULMADIĞI her durumda açıktır — `idle` yetmiyordu.
        # Kullanıcı en çok, uzun bir tur çalışırken yukarı bakmak istiyor: beş
        # dakikalık bir turun ortasında geçmişe bakamamak, kaydırmanın hiç
        # olmamasıyla aynı şey. Yalnızca modal kipler (onay, seçim) dışarıda:
        # orada oklar seçeneği gezer.
        scrollable = Condition(lambda: self._mode not in ("choice", "ask"))

        @kb.add(Keys.BracketedPaste)
        def _paste(event: object) -> None:
            # Uzun/çok-satırlı yapıştırma girdiye AKMAZ: katlanıp yer tutucuya iner,
            # tam metin gönderimde geri açılır. Tek-satır girdi kısa kalır.
            self._fold_paste(getattr(event, "data", ""))

        # Seçim kipinde Enter'ın AÇIK bağlaması olmak zorunda.
        #
        # Ölçüldü: aşağıdaki `Keys.Any` yutucusu modal kipte her tuşu yiyor ve
        # Enter girdi tamponuna hiç ulaşmıyor; tamponun accept işleyicisi bu
        # yüzden çalışmıyordu. Sonuç: onay ekranında oklar geziyor ama Enter
        # ölü — kullanıcı hiçbir şeyi onaylayamıyordu. Somut bir tuş, `Keys.Any`
        # bağından daha spesifiktir ve önce eşleşir.
        choice = Condition(lambda: self._mode == "choice")

        @kb.add("enter", filter=choice, eager=True)
        def _pick(_event: object) -> None:
            self._pick_current()

        # Onay/seçim açıkken BAŞKA hiçbir tuş girdi kutusuna ulaşmaz.
        #
        # Ölçüldü: modal açıkken yazılan metin kutuya sızıyordu. Cevap tuşları
        # (e/h) yeniyor, geri kalan harfler kutuda birikiyor ve tur bitince
        # sıradaki satır olarak GÖNDERİLİYORDU — kullanıcının cevabı, bir sonraki
        # turun görevine dönüşüyordu. O turun bütçesi de o tek harften
        # hesaplandığı için iş "araç turu sınırına ulaşıldı" ile yarıda kalıyordu.
        #
        # `ask` kipi DIŞARIDADIR: orada beklenen şey zaten serbest metindir.
        modal = Condition(lambda: self._mode == "choice")

        @kb.add(Keys.Any, filter=modal, eager=True)
        def _yut(event: object) -> None:
            """Cevap olmayan tuşu kutuya yazma; aranabilir seçicide sorguya işle (#202)."""
            char = str(getattr(event, "data", "") or "")
            if not self._choice_type(char):
                self._pick_number(char)

        @kb.add("backspace", filter=modal & Condition(self._searching), eager=True)
        def _search_back(_event: object) -> None:
            if self._choice_search is not None and self._choice_search.backspace():
                self._apply_search(self._choice_search)

        # Oklar: seçim modunda seçeneği gezer, boştayken konuşmayı kaydırır.
        nav = Condition(lambda: self._mode in ("idle", "choice"))

        # Claude Code (#196): boştayken Up/Down (Ctrl+P/Ctrl+N) çok satırda imleci, ilk/son
        # satırda dizin geçmişini gezer; konuşma PageUp/PageDown ve Shift+oklarla kayar.
        @kb.add("up", filter=nav, eager=True)
        @kb.add("c-p", filter=nav, eager=True)
        def _up(_event: object) -> None:
            if self._mode == "choice":
                self._move_choice(-1)
            elif not self._take_back_queue():
                self._input.buffer.auto_up()

        @kb.add("down", filter=nav, eager=True)
        @kb.add("c-n", filter=nav, eager=True)
        def _down(_event: object) -> None:
            self._move_choice(1) if self._mode == "choice" else self._input.buffer.auto_down()

        # Claude Code Select bağlamı (#202): seçicide J/K da gezer, Home/End uçlara gider.
        @kb.add("k", filter=modal, eager=True)
        def _select_previous(_event: object) -> None:
            if not (self._searching() and self._choice_type("k")):
                self._move_choice(-1)

        @kb.add("j", filter=modal, eager=True)
        def _select_next(_event: object) -> None:
            if not (self._searching() and self._choice_type("j")):
                self._move_choice(1)

        @kb.add("home", filter=modal, eager=True)
        def _select_first(_event: object) -> None:
            self._move_choice(-self._choice_index)

        @kb.add("end", filter=modal, eager=True)
        def _select_last(_event: object) -> None:
            self._move_choice(len(self._choices) - 1 - self._choice_index)

        # Claude Code `/copy` (#231): seçicide `w` seçimi dosyaya yazdırır.
        @kb.add("w", filter=modal & Condition(lambda: "w" in self._choice_alt_keys), eager=True)
        def _select_write(_event: object) -> None:
            if not (self._searching() and self._choice_type("w")):
                self._pick_alt("w")

        # Claude Code ModelPicker (#211): `s` yalnız oturum, sol/sağ effort.
        @kb.add("s", filter=modal & Condition(lambda: "s" in self._choice_alt_keys), eager=True)
        def _select_session(_event: object) -> None:
            if not (self._searching() and self._choice_type("s")):
                self._pick_alt("s")

        for arrow in ("left", "right"):

            def _select_arrow(_event: object, arrow: str = arrow) -> None:
                self._pick_alt(arrow)

            kb.add(
                arrow,
                filter=modal & Condition(lambda arrow=arrow: arrow in self._choice_alt_keys),
                eager=True,
            )(_select_arrow)

        # Enter gönderir, `\`+Enter yeni satır; Ctrl+J, Option+Enter, Shift+Enter yeni satır
        # (#197). Seçim kipinin Enter'ı yukarıda ayrıca bağlı.
        typing = Condition(lambda: self._mode != "choice")

        @kb.add("enter", filter=typing, eager=True)
        def _enter(_event: object) -> None:
            submit_or_newline(self._input.buffer)

        @kb.add("c-j", filter=typing, eager=True)
        def _newline(_event: object) -> None:
            self._input.buffer.insert_text("\n", fire_event=False)

        # Tekerlek dizileri (`\x1b[62~`/`\x1b[63~`) fare kipinden BAĞIMSIZ ayrıştırılır.
        @kb.add(Keys.ScrollUp, filter=scrollable, eager=True)
        def _mouse_up(_event: object) -> None:
            self._scroll_by(_SCROLL_STEP)

        @kb.add(Keys.ScrollDown, filter=scrollable, eager=True)
        def _mouse_down(_event: object) -> None:
            self._scroll_by(-_SCROLL_STEP)

        # Yeniden bağlanabilir eylemler (varsayılanlar `config/keybindings.py`'de). Escape
        # yalnız `kes` içindir ve her kipte çalışır; kaydırma eylemleri modal dışında;
        # `c-r` tarihsel olarak en başa gider (End ile canlı akışa dönülür).
        actions: dict[str, tuple[Callable[[], None], Filter | None]] = {
            "cik": (self._on_exit, None),
            "kes": (self._cancel_or_interrupt, None),
            "kes_temizle_cik": (self._ctrl_c_pressed, None),
            "cift_basista_cik": (self._ctrl_d_pressed, None),
            # Yalnız tur sürerken: boştayken Ctrl+B satır düzenlemesinde (geri karakter) kalır.
            "arka_plana_al": (self._request_background, Condition(self._can_background)),
            "kip_dongusu": (self._on_cycle_mode, None),
            "sayfa_yukari": (lambda: self._scroll_by(_SCROLL_PAGE), scrollable),
            "sayfa_asagi": (lambda: self._scroll_by(-_SCROLL_PAGE), scrollable),
            "en_bas": (self._scroll_home, scrollable),
            "en_son": (self._scroll_end, scrollable),
            "kaydir_yukari": (lambda: self._scroll_by(_SCROLL_STEP), scrollable),
            "kaydir_asagi": (lambda: self._scroll_by(-_SCROLL_STEP), scrollable),
            "simdi_gonder": (self._send_queue_now, typing),
            "dis_editor": (
                lambda: input_actions.open_external_editor(self._input.buffer),
                typing,
            ),
            "geri_al": (lambda: input_actions.undo(self._input.buffer), typing),
            "sakla": (self._toggle_stash, typing),
            "yeniden_ciz": (lambda: input_actions.redraw(self.application), None),
        }
        # Vim kipinde (P-067) Esc INSERT'ten NORMAL'e geçmelidir. Ölçüldü (31 Ekim): uygulama
        # düzeyinde eager bağlı `escape: kes` prompt_toolkit'in vi bağını eziyor, vi_state hep
        # INSERT'te kalıyordu. INSERT kipinde (seçici açık değilken) `kes` bağı devre dışı kalır;
        # NORMAL kipte ve seçicide Esc yine keser; Ctrl-C her kipte keser.
        from prompt_toolkit.filters import vi_insert_mode

        vi_typing = vi_insert_mode & Condition(lambda: self._mode != "choice")
        # Claude Code `vimInsertModeRemaps` (#217): `jj` gibi dizi INSERT'ten NORMAL'e geçer.
        if self._vim_remaps:
            vim_remaps.add_remap_bindings(kb, self._vim_remaps)
        for key, action in self._keymap.bindings(CONTEXT_TUI).items():
            if action.startswith(COMMAND_PREFIX):
                command = action[len(COMMAND_PREFIX) :].strip().lstrip("/")
                handler: Callable[[], None] = self._command_sender(command)
                condition: Filter | None = idle
            elif action in actions:
                handler, condition = actions[action]
                if action == "kes" and key == "escape":
                    condition = ~vi_typing if condition is None else condition & ~vi_typing
            else:
                continue
            try:
                self._add_action(kb, key, handler, condition)
            except ValueError:
                # Bilinmeyen tuş adı: `/keybindings` uyarır, öteki bağlar çalışmaya devam eder.
                continue

        return kb

    def _command_sender(self, command: str) -> Callable[[], None]:
        """`komut:<ad>` bağı: tuşa basınca `/ad` gönderilir (döngü değişkeni kapanmaz)."""

        def _send() -> None:
            self._on_submit(f"/{command}")

        return _send

    @staticmethod
    def _add_action(
        kb: KeyBindings, key: str, handler: Callable[[], None], condition: Filter | None
    ) -> None:
        def _run(_event: object) -> None:
            handler()

        # Chord (#194): `c-x c-e` prompt_toolkit'e tuş dizisi olarak verilir.
        keys = key.split(" ") if key != " " else [key]
        if condition is None:
            kb.add(*keys, eager=True)(_run)
        else:
            kb.add(*keys, filter=condition, eager=True)(_run)

    def set_queue_hooks(
        self, take_back: Callable[[], list[str]], send_now: Callable[[str], None]
    ) -> None:
        """Kuyruk kancaları (#190): ilk satırda Up geri alır, chat:sendNow hemen yollar."""
        self._take_back = take_back
        self._send_now = send_now

    def _take_back_queue(self) -> bool:
        """İlk satırda Up: kuyruktakileri taslağın önüne koy (Claude Code ile aynı)."""
        buffer = self._input.buffer
        if self._take_back is None or buffer.document.cursor_position_row != 0:
            return False
        taken = self._take_back()
        if not taken:
            return False
        text = input_actions.take_back_text(taken, buffer.text)
        buffer.text = text
        buffer.cursor_position = len(text)
        return True

    def _send_queue_now(self) -> None:
        """chat:sendNow: kuyruğu hemen yolla; yazılmış taslak arkasına kuyruklanır."""
        if self._send_now is None:
            return
        draft = self._input.buffer.text
        self._input.buffer.reset()
        self._send_now(draft)

    def _toggle_stash(self) -> None:
        if self._stash.toggle(self._input.buffer):
            self.application.invalidate()

    def _ctrl_c_pressed(self) -> None:
        """Ctrl+C: modalı kapatır, turu keser; boştayken girdiyi temizler, ikincisi çıkar."""
        if self._mode in ("ask", "choice") or self._is_busy():
            self._ctrl_c.reset()
            self._cancel_or_interrupt()
            return
        if self._input.buffer.text:
            # Claude Code (#195): ilk basış girdiyi temizler (taslak Up ile geri gelir),
            # pencere içindeki ikinci basış çıkar.
            self._clear_into_history()
            self._ctrl_c.reset()
            self._ctrl_c.press()
            self._show_flash(messages.TUI_PRESS_AGAIN_TO_EXIT.format(key="Ctrl+C"))
            return
        if self._ctrl_c.press():
            self._on_exit()
            return
        self._show_flash(messages.TUI_PRESS_AGAIN_TO_EXIT.format(key="Ctrl+C"))

    def _ctrl_d_pressed(self) -> None:
        """Ctrl+D: girdi doluysa sonraki karakteri siler; boşken 800 ms'de iki basış çıkar."""
        buffer = self._input.buffer
        if buffer.text:
            self._ctrl_d.reset()
            buffer.delete(1)
            return
        if self._ctrl_d.press():
            self._on_exit()
            return
        self._show_flash(messages.TUI_PRESS_AGAIN_TO_EXIT.format(key="Ctrl+D"))

    def _show_flash(self, text: str) -> None:
        self._flash = text
        self._refresh_status()
        loop = self.application.loop if self.application.is_running else None
        if loop is not None:
            loop.call_later(DOUBLE_PRESS_SECONDS, self._clear_flash)

    def _clear_flash(self) -> None:
        self._flash = ""
        self._refresh_status()

    def _can_background(self) -> bool:
        return self._on_background is not None and self._work_source is not None

    def _request_background(self) -> None:
        if self._on_background is not None:
            self._on_background()

    def _cancel_or_interrupt(self) -> None:
        if self._mode == "ask":
            self._resolve("")
        elif self._mode == "choice":
            # Aranabilir seçicide ilk Esc arama kipinden çıkar (#202), ikincisi kapatır.
            if self._choice_search is not None and self._choice_search.exit():
                self._apply_search(self._choice_search)
            else:
                self._resolve(None)
        elif self._rewind_requested():
            self._on_rewind()  # type: ignore[misc]  # `_rewind_requested` None'ı eledi
        elif self._clear_requested():
            self._clear_into_history()
        else:
            self._on_interrupt()

    def _clear_requested(self, *, now: float | None = None) -> bool:
        """Boştayken DOLU girdide art arda iki Esc mi? (Claude Code #222: girdiyi temizler.)

        Tur sürerken Esc her zaman keser; girdi boşsa bu karar `_rewind_requested`'indir.
        """
        if self._is_busy() or not self._input.text.strip():
            self._last_clear_escape_at = 0.0
            return False
        stamp = time.monotonic() if now is None else now
        is_double = 0.0 < stamp - self._last_clear_escape_at <= DOUBLE_ESCAPE_SECONDS
        self._last_clear_escape_at = 0.0 if is_double else stamp
        return is_double

    def _clear_into_history(self) -> None:
        """Girdiyi temizle; taslak dizin geçmişine yazılır, Up ile geri gelir (#222)."""
        buffer = self._input.buffer
        draft = self._expand_pastes(buffer.text)
        buffer.reset()
        if draft.strip():
            remember = getattr(buffer.history, "remember_draft", None)
            if remember is not None:
                remember(draft)
            else:
                buffer.history.append_string(draft)

    def _rewind_requested(self, *, now: float | None = None) -> bool:
        """Boş girdide art arda iki Esc mi? (Claude Code: Esc Esc → `/rewind`.)

        Tur çalışırken ilk Esc turu keser (eski davranış); kesmeden sonra gelen ikinci
        Esc de pencere içindeyse geri sarma açılır. Girdi doluysa Esc hiçbir şey açmaz.
        """
        if self._on_rewind is None or self._input.text.strip():
            self._last_escape_at = 0.0
            return False
        stamp = time.monotonic() if now is None else now
        is_double = 0.0 < stamp - self._last_escape_at <= DOUBLE_ESCAPE_SECONDS
        self._last_escape_at = 0.0 if is_double else stamp
        return is_double

    def _invalidate(self) -> None:
        if self.application.is_running:
            self.application.invalidate()


def _log_spinner_result(task: asyncio.Task[None]) -> None:
    """Spinner arka planda çalışır; iptal beklenendir, başka hata yutulmaz."""
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        _logger.warning("çalışma satırı spinner'ı beklenmedik biçimde durdu: %s", error)


def _term_width() -> int:
    return max(20, shutil.get_terminal_size((100, 40)).columns)


def _term_rows() -> int:
    return max(10, shutil.get_terminal_size((100, 40)).lines)

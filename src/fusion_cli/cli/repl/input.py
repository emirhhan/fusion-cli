"""İnteraktif giriş — prompt_toolkit sarmalayıcısı.

Terminal TTY değilse (boru hattı, CI, test) prompt_toolkit hiç kurulmaz ve düz
`input()`'a düşülür; otomasyon kırılmaz.

İki tasarım kararı görüntüyü belirler:

1. **Giriş satırı ve çalışan tur ASLA aynı anda ekranda olmaz.** Tur çalışırken
   prompt kapalıdır; çalışan turu Ctrl-C keser.

2. **Ekranın altında yalnızca TEK satır ayrılır.** Yeniden boyutlandırmada prompt
   kopyalarının ekranda birikmesinin sebebi, tamamlama menüsü için varsayılan
   olarak ayrılan 8 satırdı: terminal küçüldüğünde bu blok doğru silinemiyordu.
   Menü rezervasyonu kapatıldı; durum çubuğu tek satır olduğu için yeniden çizim
   güvenli.

3. **Uzun yapıştırma tampona GİRMEZ.** prompt_toolkit her belge satırı için bir
   ekran satırı çizer; 200 satırlık bir yapıştırma giriş penceresini 200 satıra
   büyütüp konuşmayı ekrandan yukarı iterdi. Bir `Processor` yalnızca satır
   içeriğini değiştirebilir, satır SAYISINI değiştiremez — bu yüzden görsel
   katlama yüksekliği düşürmezdi. Çözüm: yapıştırma yakalanır, gerçek metin yan
   bir tabloda saklanır ve tampona tek satırlık bir yer tutucu konur; satır
   gönderilirken yer tutucu tam metne geri açılır. Böylece model tam metni alır,
   giriş alanı tek satır kalır.

3. **Durum çubuğunun ters-renkli zemini yok.** prompt_toolkit'in varsayılan
   `bottom-toolbar` stili tam genişlikte beyaz bir şerit çiziyordu. Stil
   geçersiz kılınarak sönük, zeminsiz bir satıra indirildi.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...config import keybindings
from ...engines.agent.approval import ApprovalMode, next_mode
from ...ui import messages, theme

#: Yapıştırma bu satır ya da bu karakter sayısını aşarsa tek satırlık yer tutucuya
#: katlanır (ikisinden biri yeterli). Karakter eşiği, az satırlı ama çok uzun tek
#: satırlık yapıştırmaları da yakalar (Claude'un davranışına benzer).
FOLD_PASTE_LINES = 10
FOLD_PASTE_CHARS = 600

#: Giriş satırının başındaki işaret. Kısa tutulur: her satırda tekrarlanır.
PROMPT_SYMBOL = "❯"

#: Durum çubuğunda modun önüne konan işaret.
STATUS_MARK = "⏵"
#: Vim kipi açıkken istemin önündeki etiket.
VIM_LABEL = "vim"


class ReplInput:
    """Komut geçmişi, tamamlama ve shift-tab ile mod döngüsü sunan giriş."""

    def __init__(
        self,
        history_path: Path,
        words: list[str] | Callable[[], list[str]],
        *,
        mode: ApprovalMode,
        roots: tuple[Path, ...] = (),
    ) -> None:
        """`words` bir çağrılabilir olabilir: tamamlama sözlüğü her istemde yeniden alınır.

        Ölçüldü (31 Ekim): sözlük başlangıçta bir kez alınıyordu; `/skills new`, `/skills
        reload` ya da `/add-dir` ile eklenen beceri `/ad` olarak çalışıyor ama Tab
        tamamlamada görünmüyordu.
        """
        self.mode = mode
        #: `@yol` tamamlamasının gezineceği kökler (proje kökü + `--add-dir`).
        self.roots = roots
        #: Vim düzenleme kipi (P-067); REPL `runtime.vim_mode`'dan eşler.
        self.vim_mode = False
        #: `komut:<ad>` tuş bağı gönderilen komutu buraya bırakır; `prompt()` onu satır yapar.
        self._bound_command: str | None = None
        #: Tuş tablosu (P-067): dosya değişince `prompt()` yeniden yükler.
        self._keymap = keybindings.load_keymap()
        self._bindings: Any = None
        #: Durum çubuğunda gösterilen bağlam. REPL her değişiklikte günceller.
        self.context: str = ""
        #: Kullanıcı betiğinin ürettiği durum satırı (P-069); doluysa bağlamın yerine geçer.
        self.custom_status: str = ""
        self._session: Any = None
        self._fold_paste = True
        #: Katlanan yapıştırmaların yer tutucu → tam metin eşlemesi. Her satır
        #: gönderiminden önce temizlenir; yalnızca o satır boyunca yaşar.
        self._pastes: dict[str, str] = {}
        self._paste_seq = 0
        #: İstem açık mı? `inject` yalnız bu sırada satır verebilir.
        self._waiting = False
        if sys.stdin.isatty():
            self._session = _build_session(self, history_path, words, roots)

    @property
    def interactive(self) -> bool:
        return self._session is not None

    def cycle_mode(self) -> ApprovalMode:
        self.mode = next_mode(self.mode)
        return self.mode

    def toggle_fold(self) -> None:
        self._fold_paste = not self._fold_paste

    @property
    def fold_paste(self) -> bool:
        return self._fold_paste

    def fold_paste_into(self, buffer: Any, text: str) -> None:
        """Yapıştırmayı tampona koy. Uzunsa metni saklayıp yer tutucu bırakır.

        Kısa yapıştırma (eşik altı) ya da katlama kapalıysa metin olduğu gibi
        eklenir — eski davranış. Uzunsa tampona yalnızca tek satırlık bir yer
        tutucu girer; gerçek metin `_pastes`'te saklanır ve gönderimde açılır.
        """
        line_count = text.count("\n") + 1
        long_enough = line_count > FOLD_PASTE_LINES or len(text) > FOLD_PASTE_CHARS
        if not self._fold_paste or not long_enough:
            buffer.insert_text(text)
            return
        self._paste_seq += 1
        # Çok satırlıysa satır sayısı daha anlamlı; tek satırlık uzun yapıştırmada
        # "1 satır" yanıltıcı olur, karakter sayısı gösterilir.
        if line_count > 1:
            token = messages.REPL_PASTE_FOLDED.format(count=line_count, index=self._paste_seq)
        else:
            token = messages.REPL_PASTE_FOLDED_CHARS.format(count=len(text), index=self._paste_seq)
        self._pastes[token] = text
        buffer.insert_text(token)

    def expand_pastes(self, line: str) -> str:
        """Satırdaki yer tutucuları sakladıkları tam metinle değiştir."""
        for token, text in self._pastes.items():
            line = line.replace(token, text)
        return line

    def inject(self, line: str) -> bool:
        """Bekleyen istemi bu satırla sonlandır (zamanlanmış görev, P-038).

        Yalnız etkileşimli istem BOŞ beklerken çalışır; aksi hâlde False döner ve
        çağıran görevi düşürmez, sonraki boşta ana bırakır. Ölçüldü (31 Ekim): tampon
        doluyken `app.exit` kullanıcının yarım yazdığı satırı atıyordu.
        """
        if self._session is None or not self._waiting:
            return False
        app = self._session.app
        if not app.is_running or app.current_buffer.text.strip():
            return False
        app.exit(result=line)
        return True

    async def prompt(self) -> str:
        # Yer tutucular yalnızca içinde bulunulan satır boyunca geçerli.
        self._pastes.clear()
        if self._session is None:
            # Düz `input()` bloklar; ayrı bir thread'e alınmazsa arka plandaki
            # öğrenme işleri kullanıcı yazarken ilerleyemez.
            # İşaret basılmaz: kullanıcı mesajı zaten bant olarak çiziliyor.
            return await asyncio.to_thread(input, "")
        # Mesaj CALLABLE verilir: shift-tab modu değiştirip `invalidate()` çağırınca
        # prompt_toolkit mesajı YENİDEN hesaplar ve mod etiketi ANINDA güncellenir.
        # Statik `HTML(...)` verilseydi etiket bir sonraki Enter'a kadar donardı.
        self._reload_keymap_if_changed()
        self._session.editing_mode = _editing_mode(self.vim_mode)
        self._waiting = True
        try:
            line = await self._session.prompt_async(self._prompt_message)
        finally:
            self._waiting = False
        if self._bound_command is not None:
            # Tuşa bağlı komut (`komut:<ad>`): yazılan metin yerine o komut gönderilir.
            bound, self._bound_command = self._bound_command, None
            return bound
        return self.expand_pastes(str(line))

    def _reload_keymap_if_changed(self) -> None:
        if keybindings.has_changed(self._keymap):
            self._keymap = keybindings.load_keymap(self._keymap.path)
            self._bindings = build_input_bindings(self, self._keymap)

    @property
    def keymap(self) -> keybindings.KeyMap:
        return self._keymap

    def run_bound_command(self, command: str, event: Any) -> None:
        """`komut:<ad>` bağı: `/ad` satırını gönder (tampondaki metin korunmaz)."""
        self._bound_command = f"/{command.strip().lstrip('/')}"
        event.current_buffer.validate_and_handle()

    def _prompt_message(self) -> Any:
        """İstem satırının o anki HTML biçimi (her yeniden çizimde çağrılır)."""
        from prompt_toolkit.formatted_text import HTML

        return HTML(prompt_fragments(self.mode, vim=self.vim_mode))

    def status_bar(self) -> Any:
        """Ekranın altındaki tek satırlık durum çubuğu.

        Her yeniden çizimde çağrılır; shift-tab ile mod değişince kendiliğinden
        güncellenir.
        """
        from prompt_toolkit.formatted_text import HTML

        color = theme.MODE_COLORS.get(self.mode.value, theme.DIM)
        context = self.custom_status or self.context
        parts = [
            f"<style fg='{color}'>{STATUS_MARK} {self.mode.value}</style>",
            f"<style fg='{theme.DIM}'>{_escape_html(context)}</style>" if context else "",
            f"<style fg='{theme.DIM}'>{messages.REPL_ON_OFF_HINT}</style>",
        ]
        separator = f"<style fg='{theme.DIM}'> · </style>"
        return HTML(" " + separator.join(part for part in parts if part))


def _escape_html(text: str) -> str:
    """Betik çıktısı prompt_toolkit HTML'ine ham girmesin."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def toolbar_enabled() -> bool:
    """Alt bilgi çubuğu gösterilsin mi?

    prompt_toolkit #1933: terminal yeniden boyutlandırılınca istem ekranda
    kopyalanıyor. Kök neden `renderer.erase()`'in GÖRELİ imleç hareketidir: tam
    genişlikteki `bottom_toolbar` daralmada iki satıra sarınca `cursor_up` eksik
    kalıyor ve eski istem silinemiyor.

    Varsayılan KAPALI. `FUSION_TOOLBAR=1` geri getirir; o modda resize'da istem
    kopyaları yeniden görünür.
    """
    import os

    return os.environ.get("FUSION_TOOLBAR", "") == "1"


def _build_session(
    owner: ReplInput,
    history_path: Path,
    words: list[str] | Callable[[], list[str]],
    roots: tuple[Path, ...] = (),
) -> Any:
    """prompt_toolkit oturumunu kur. Kurulamazsa None → düz girişe düşülür."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import DynamicKeyBindings

        from .completion import ReplCompleter

        history_path.parent.mkdir(parents=True, exist_ok=True)
        # Bağlar tablodan üretilir ve dosya değişince yenilenir (P-067): `DynamicKeyBindings`
        # her tuşta o anki tabloyu okur, oturumu yeniden kurmak gerekmez.
        owner._bindings = build_input_bindings(owner, owner.keymap)
        bindings = DynamicKeyBindings(lambda: owner._bindings)

        return PromptSession(
            history=FileHistory(str(history_path)),
            # `/komut` ve `@yol` tamamlama tek tamamlayıcıda (P-022); sözlük çağrılabilir olabilir,
            # dinamik beceri komutları eklendikçe tamamlama da yenilenir (P-019).
            completer=ReplCompleter(words, roots),
            # Alt bilgi çubuğu VARSAYILAN OLARAK KAPALI: tam genişlikte olduğu için
            # terminal daraldığında sarıyor ve resize'da istem kopyası bırakıyordu.
            # Mod bilgisi istemin kendisine taşındı. FUSION_TOOLBAR=1 geri getirir.
            bottom_toolbar=owner.status_bar if toolbar_enabled() else None,
            style=_toolbar_style(),
            # Girilen satır prompt_toolkit tarafından SİLİNİR; kullanıcı mesajını
            # kendimiz tam genişlikte bir bant olarak çiziyoruz (bkz. ui.renderer).
            erase_when_done=True,
            # Tamamlama Tab ile açılır. Yazarken açılması hem gürültülüdür hem de
            # menü için ekran altında yer ayrılmasına yol açar.
            complete_while_typing=False,
            # Menü için HİÇ yer ayrılmaz: ayrılan satırlar yeniden boyutlandırmada
            # doğru silinemiyor ve prompt kopyaları ekranda birikiyordu.
            reserve_space_for_menu=0,
            key_bindings=bindings,
        )
    except Exception:
        # prompt_toolkit kurulamadı (terminal desteklemiyor, ortam kısıtlı…).
        # Düz girişe düşmek kabul edilebilir; REPL çalışmaya devam etmelidir.
        return None


def build_input_bindings(owner: ReplInput, keymap: keybindings.KeyMap) -> Any:
    """Satır-içi istemin tuş bağlarını tablodan kur (P-067).

    Yapıştırma yakalayıcısı tabloda DEĞİLDİR: eylem değil, girdinin çalışma biçimidir.
    Geçersiz tuş adı tek bağı düşürür, oturumu değil.
    """
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.keys import Keys

    bindings = KeyBindings()

    def _cycle(event: Any) -> None:
        owner.cycle_mode()
        event.app.invalidate()

    def _fold(event: Any) -> None:
        owner.toggle_fold()
        event.app.invalidate()

    actions: dict[str, Callable[[Any], None]] = {
        "kip_dongusu": _cycle,
        "yapistirma_katla": _fold,
    }
    for key, action in keymap.bindings(keybindings.CONTEXT_INPUT).items():
        handler = _resolve_action(owner, action, actions)
        if handler is None:
            continue
        try:
            bindings.add(key)(handler)
        except ValueError:
            # Bilinmeyen tuş adı: `/keybindings` dosyayı gösterir, kullanıcı düzeltir.
            continue

    @bindings.add(Keys.BracketedPaste)
    def _paste(event: Any) -> None:
        # Yapıştırma varsayılan olarak tampona AKMAZ: uzunsa metin saklanır ve
        # yerine tek satırlık yer tutucu konur (bkz. modül başlığı, madde 3).
        owner.fold_paste_into(event.current_buffer, event.data)

    return bindings


def _resolve_action(
    owner: ReplInput, action: str, actions: dict[str, Callable[[Any], None]]
) -> Callable[[Any], None] | None:
    if action.startswith(keybindings.COMMAND_PREFIX):
        command = action[len(keybindings.COMMAND_PREFIX) :]
        return lambda event: owner.run_bound_command(command, event)
    return actions.get(action)


def _editing_mode(vim: bool) -> Any:
    from prompt_toolkit.enums import EditingMode

    return EditingMode.VI if vim else EditingMode.EMACS


def _toolbar_style() -> Any:
    """Durum çubuğunun varsayılan ters-renkli zeminini kaldır.

    prompt_toolkit `bottom-toolbar` için açık gri zemin + siyah yazı kullanır; bu
    terminalin altında dikkat çeken çirkin bir şerit oluşturuyor. Sönük ve
    zeminsiz bir satır, bilgiyi verir ama gözü çekmez.
    """
    from prompt_toolkit.styles import Style

    return Style.from_dict(
        {
            "bottom-toolbar": "noreverse bg:default",
            "bottom-toolbar.text": "noreverse bg:default",
        }
    )


def prompt_fragments(mode: Any, *, vim: bool = False) -> str:
    """İstem satırının HTML biçimli hali: mod etiketi + istem sembolü.

    Mod bilgisi eskiden tam genişlikte bir alt bilgi çubuğundaydı. O çubuk terminal
    daraldığında SARIYOR ve prompt_toolkit'in resize silme aritmetiğini bozuyordu
    (#1933: `erase()` imleci bayat `cursor_up(y)` ile geri alıyor). Bilgi istemin
    kendisine alındı: aynı satırda kalır, sarmaz, kopya bırakmaz.

    `auto` VARSAYILAN olduğu için etiketi yazılmaz: istem sade kalır (yalnızca sembol)
    ve resize kopyası riski en düşüktür. `auto` DIŞINDAKİ modlarda kısa, renkli bir
    etiket öne konur. Bu, shift-tab'ın GÖRÜNÜR geri bildirimidir: toolbar varsayılan
    kapalı olduğundan ve etiket buradan da kaldırıldığından, mod dönüyor ama ekranda
    hiçbir şey değişmiyordu — kullanıcı shift-tab'ı ölü sanıyordu. En uzun etiket
    ("security ❯ ") 11 görünür karakterdir; `test_istem_tek_satir_kalir`'in sınırı içindedir.
    """
    symbol = f"<style fg='{theme.ACCENT}'><b>{PROMPT_SYMBOL}</b></style> "
    # Vim kipi (P-067) kısa bir etiketle görünür; etiket yine tek satırda kalır.
    vim_label = f"<style fg='{theme.DIM}'>{VIM_LABEL}</style> " if vim else ""
    value = getattr(mode, "value", "")
    if value == "auto" or not value:
        return vim_label + symbol
    color = theme.MODE_COLORS.get(value, theme.DIM)
    return f"{vim_label}<style fg='{color}'>{value}</style> {symbol}"

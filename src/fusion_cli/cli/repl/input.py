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

3. **Durum çubuğunun ters-renkli zemini yok.** prompt_toolkit'in varsayılan
   `bottom-toolbar` stili tam genişlikte beyaz bir şerit çiziyordu. Stil
   geçersiz kılınarak sönük, zeminsiz bir satıra indirildi.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from ...engines.agent.approval import ApprovalMode
from ...ui import messages, theme

#: Yapıştırılan metin bu satırdan uzunsa katlanarak tek satırda özetlenir.
FOLD_PASTE_LINES = 10

#: Giriş satırının başındaki işaret. Kısa tutulur: her satırda tekrarlanır.
PROMPT_SYMBOL = "❯"

#: Durum çubuğunda modun önüne konan işaret.
STATUS_MARK = "⏵"

#: Onay modunun durum çubuğundaki rengi — riskli mod göze çarpsın.
_MODE_COLORS = {"auto": theme.OK, "plan": theme.WARN, "security": theme.ERROR}


class ReplInput:
    """Komut geçmişi, tamamlama ve shift-tab ile mod döngüsü sunan giriş."""

    def __init__(self, history_path: Path, words: list[str], *, mode: ApprovalMode) -> None:
        self.mode = mode
        #: Durum çubuğunda gösterilen bağlam. REPL her değişiklikte günceller.
        self.context: str = ""
        self._session: Any = None
        self._fold_paste = True
        if sys.stdin.isatty():
            self._session = _build_session(self, history_path, words)

    @property
    def interactive(self) -> bool:
        return self._session is not None

    def cycle_mode(self) -> ApprovalMode:
        modes = tuple(ApprovalMode)
        self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
        return self.mode

    def toggle_fold(self) -> None:
        self._fold_paste = not self._fold_paste

    @property
    def fold_paste(self) -> bool:
        return self._fold_paste

    async def prompt(self) -> str:
        if self._session is None:
            # Düz `input()` bloklar; ayrı bir thread'e alınmazsa arka plandaki
            # öğrenme işleri kullanıcı yazarken ilerleyemez.
            # İşaret basılmaz: kullanıcı mesajı zaten bant olarak çiziliyor.
            return await asyncio.to_thread(input, "")
        from prompt_toolkit.formatted_text import HTML

        line = await self._session.prompt_async(
            HTML(f"<style fg='{theme.ACCENT}'><b>{PROMPT_SYMBOL}</b></style> ")
        )
        return str(line)

    def status_bar(self) -> Any:
        """Ekranın altındaki tek satırlık durum çubuğu.

        Her yeniden çizimde çağrılır; shift-tab ile mod değişince kendiliğinden
        güncellenir.
        """
        from prompt_toolkit.formatted_text import HTML

        color = _MODE_COLORS.get(self.mode.value, theme.DIM)
        parts = [
            f"<style fg='{color}'>{STATUS_MARK} {self.mode.value}</style>",
            f"<style fg='{theme.DIM}'>{self.context}</style>" if self.context else "",
            f"<style fg='{theme.DIM}'>{messages.REPL_ON_OFF_HINT}</style>",
        ]
        separator = f"<style fg='{theme.DIM}'> · </style>"
        return HTML(" " + separator.join(part for part in parts if part))


def _build_session(owner: ReplInput, history_path: Path, words: list[str]) -> Any:
    """prompt_toolkit oturumunu kur. Kurulamazsa None → düz girişe düşülür."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import KeyBindings

        history_path.parent.mkdir(parents=True, exist_ok=True)
        bindings = KeyBindings()

        @bindings.add("s-tab")
        def _cycle(event: Any) -> None:
            owner.cycle_mode()
            event.app.invalidate()

        @bindings.add("c-v")
        def _fold(event: Any) -> None:
            owner.toggle_fold()
            event.app.invalidate()

        return PromptSession(
            history=FileHistory(str(history_path)),
            completer=WordCompleter(words, sentence=True),
            bottom_toolbar=owner.status_bar,
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
            input_processors=[_paste_fold_processor(owner)],
        )
    except Exception:
        # prompt_toolkit kurulamadı (terminal desteklemiyor, ortam kısıtlı…).
        # Düz girişe düşmek kabul edilebilir; REPL çalışmaya devam etmelidir.
        return None


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


def _paste_fold_processor(owner: ReplInput) -> Any:
    """Uzun yapıştırmaları tek satırlık özete katlayan işleyici.

    Sınıf çalışma anında kurulur: `prompt_toolkit.Processor` taban sınıfı ancak
    kütüphane yüklendiğinde erişilebilirdir ve bu modül TTY olmayan ortamlarda
    kütüphaneyi hiç yüklememelidir.
    """
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.layout.processors import Processor, Transformation

    class PasteFold(Processor):
        def apply_transformation(self, transformation_input: Any) -> Any:
            lines = transformation_input.document.lines
            if not owner.fold_paste or len(lines) <= FOLD_PASTE_LINES:
                return Transformation(transformation_input.fragments)
            if transformation_input.lineno == 0:
                summary = messages.REPL_PASTE_FOLDED.format(count=len(lines))
                return Transformation(FormattedText([("class:dim italic", summary)]))
            return Transformation(FormattedText([]))

    return PasteFold()

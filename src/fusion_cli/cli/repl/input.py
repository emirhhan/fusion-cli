"""İnteraktif giriş — prompt_toolkit sarmalayıcısı.

Terminal TTY değilse (boru hattı, CI, test) prompt_toolkit hiç kurulmaz ve düz
`input()`'a düşülür; otomasyon kırılmaz.

İki tasarım kararı görüntüyü belirler:

1. **Giriş satırı ve çalışan tur ASLA aynı anda ekranda olmaz.** Tur çalışırken
   prompt kapalıdır; çalışan turu Ctrl-C keser.

2. **Durum bilgisi alta sabitlenmiş bir widget DEĞİL, sol prompt'un parçasıdır.**
   Eskiden durum bir `bottom_toolbar` idi; alta sabitlenmiş bu ayrı widget, terminal
   yeniden boyutlandırıldığında (özellikle geçmiş tamponunu yeniden saran Terminal.app
   / iTerm'de) prompt_toolkit'in bayat imleç modeliyle yaptığı silmeyi ıskalatıp `❯`
   kopyalarını ekranda biriktiriyordu. Durum, giriş satırının içine (❯'nin soluna)
   alınınca o çok-satırlı widget ortadan kalkar ve yeniden boyutlandırma temiz kalır —
   ölçümle doğrulandı (bkz. prompt_message). Tamamlama menüsü rezervasyonu da kapalıdır
   (`reserve_space_for_menu=0`).

3. **Uzun yapıştırma tampona GİRMEZ.** prompt_toolkit her belge satırı için bir
   ekran satırı çizer; 200 satırlık bir yapıştırma giriş penceresini 200 satıra
   büyütüp konuşmayı ekrandan yukarı iterdi. Bir `Processor` yalnızca satır
   içeriğini değiştirebilir, satır SAYISINI değiştiremez — bu yüzden görsel
   katlama yüksekliği düşürmezdi. Çözüm: yapıştırma yakalanır, gerçek metin yan
   bir tabloda saklanır ve tampona tek satırlık bir yer tutucu konur; satır
   gönderilirken yer tutucu tam metne geri açılır. Böylece model tam metni alır,
   giriş alanı tek satır kalır.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from ...engines.agent.approval import ApprovalMode
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
        #: Katlanan yapıştırmaların yer tutucu → tam metin eşlemesi. Her satır
        #: gönderiminden önce temizlenir; yalnızca o satır boyunca yaşar.
        self._pastes: dict[str, str] = {}
        self._paste_seq = 0
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
            token = messages.REPL_PASTE_FOLDED_CHARS.format(
                count=len(text), index=self._paste_seq
            )
        self._pastes[token] = text
        buffer.insert_text(token)

    def expand_pastes(self, line: str) -> str:
        """Satırdaki yer tutucuları sakladıkları tam metinle değiştir."""
        for token, text in self._pastes.items():
            line = line.replace(token, text)
        return line

    async def prompt(self) -> str:
        # Yer tutucular yalnızca içinde bulunulan satır boyunca geçerli.
        self._pastes.clear()
        if self._session is None:
            # Düz `input()` bloklar; ayrı bir thread'e alınmazsa arka plandaki
            # öğrenme işleri kullanıcı yazarken ilerleyemez.
            # İşaret basılmaz: kullanıcı mesajı zaten bant olarak çiziliyor.
            return await asyncio.to_thread(input, "")
        # Mesaj bir callable olarak verilir: shift-tab modu değiştirip invalidate
        # edince prompt_toolkit yeniden çağırır ve durum canlı güncellenir.
        line = await self._session.prompt_async(self.prompt_message)
        return self.expand_pastes(str(line))

    def prompt_message(self) -> Any:
        """Giriş satırının sol prompt'u: durum bilgisi + `❯` işareti.

        Durum eskiden ekranın altında ayrı bir `bottom_toolbar` idi. Ayrı, alta
        sabitlenmiş bir widget, terminal yeniden boyutlandırıldığında (özellikle
        reflow eden emülatörlerde) prompt_toolkit'in bayat imleç modeliyle yaptığı
        silmeyi ıskalatıp `❯` kopyalarını ekranda biriktiriyordu. Durum, giriş
        satırının PARÇASI olarak çizilince o çok-satırlı widget ortadan kalkar ve
        yeniden boyutlandırma temiz kalır (ölçümle doğrulandı).

        Her yeniden çizimde çağrılır; mod değişince kendiliğinden güncellenir.
        """
        from prompt_toolkit.formatted_text import HTML

        return HTML(
            f"{self.status_line()} <style fg='{theme.ACCENT}'><b>{PROMPT_SYMBOL}</b></style> "
        )

    def status_line(self) -> str:
        """Sol prompt'taki durum parçası (mod + bağlam). İpucu burada gösterilmez;
        o `/help` ve karşılama kutusunda yaşar — inline'da giriş genişliğini yer."""
        color = _MODE_COLORS.get(self.mode.value, theme.DIM)
        parts = [f"<style fg='{color}'>{STATUS_MARK} {self.mode.value}</style>"]
        if self.context:
            parts.append(f"<style fg='{theme.DIM}'>{self.context}</style>")
        separator = f"<style fg='{theme.DIM}'> · </style>"
        return separator.join(parts)


def _build_session(owner: ReplInput, history_path: Path, words: list[str]) -> Any:
    """prompt_toolkit oturumunu kur. Kurulamazsa None → düz girişe düşülür."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.keys import Keys

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

        @bindings.add(Keys.BracketedPaste)
        def _paste(event: Any) -> None:
            # Yapıştırma varsayılan olarak tampona AKMAZ: uzunsa metin saklanır ve
            # yerine tek satırlık yer tutucu konur (bkz. modül başlığı, madde 3).
            owner.fold_paste_into(event.current_buffer, event.data)

        return PromptSession(
            history=FileHistory(str(history_path)),
            completer=WordCompleter(words, sentence=True),
            # Durum çubuğu bir bottom_toolbar DEĞİL: alta sabitlenmiş widget yeniden
            # boyutlandırmada ❯ kopyaları biriktiriyordu. Durum artık sol prompt'un
            # parçası (bkz. prompt_message).
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

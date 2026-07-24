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

from typing import Any

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document

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

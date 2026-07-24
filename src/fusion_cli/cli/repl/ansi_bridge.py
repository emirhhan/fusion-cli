"""Metin köprüsü — Rich render mantığını yeniden yazmadan tam-ekrana taşır.

`ConsoleRenderer` bir Rich `Console`'a yazar. Burada o console'u stdout yerine bir
`StringIO`'ya bağlarız. Böylece markdown/tablo/liste gibi tüm YERLEŞİM
biçimlendirmesi metin olarak birikir ve konuşma alanına akıtılabilir.

Not: Şu an DÜZ METİN üretiyoruz (force_terminal yok → renk kodu yok). Konuşma
alanı düz metin `TextArea` olduğundan ANSI renk kodları ham kaçış olarak görünürdü;
bu yüzden renk devre dışı. Renkli çıktı (ANSI'yi çözen kaydırılabilir kontrol) Faz
4'te ayrı bir spike ile geri gelecek — bkz. docs/BACKLOG.md.
"""

from __future__ import annotations

import io

from rich.console import Console


class AnsiBridge:
    """Rich çıktısını düz metne çeviren tamponlu köprü."""

    def __init__(self) -> None:
        self._buffer = io.StringIO()
        # Düz metin: force_terminal YOK → renk kodu üretilmez (TextArea ham kaçış
        # gösterirdi). soft_wrap: satırları Rich sarmasın; sarma prompt_toolkit'te.
        self._console = Console(file=self._buffer, soft_wrap=True)
        self._text = ""
        self._okundu = 0

    @property
    def console(self) -> Console:
        return self._console

    @property
    def text(self) -> str:
        return self._text

    def drain(self) -> str:
        """StringIO'da biriken yeni delta'yı döndür ve toplam metne ekle."""
        tumu = self._buffer.getvalue()
        delta = tumu[self._okundu :]
        self._okundu = len(tumu)
        self._text += delta
        return delta

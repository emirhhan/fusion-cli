"""ANSI köprüsü — Rich render mantığını yeniden yazmadan tam-ekrana taşır.

`ConsoleRenderer` bir Rich `Console`'a yazar. Burada o console'u stdout yerine bir
`StringIO`'ya bağlarız ve `force_terminal=True` ile renk üretmesini sağlarız.
Böylece tüm biçimlendirme (markdown, kod, tablo, renkli diff) ANSI olarak birikir
ve konuşma alanına akıtılabilir.
"""

from __future__ import annotations

import io

from rich.console import Console


class AnsiBridge:
    """Rich çıktısını ANSI metnine çeviren tamponlu köprü."""

    def __init__(self) -> None:
        self._buffer = io.StringIO()
        # force_terminal: StringIO'da bile renk üret. soft_wrap: satırları Rich
        # kendisi sarmasın; sarma prompt_toolkit tarafında yapılır.
        self._console = Console(file=self._buffer, force_terminal=True, soft_wrap=True)
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

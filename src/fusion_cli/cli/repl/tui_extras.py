"""Tam ekran TUI'nin #216 genel kısayol durumu: transcript görünümü, görüntü çipleri,
Option+harf eylemleri.

`FusionTui` bu nesneyi tutar; döngü (`tui_loop`) kaynakları bağlar. Ayrı modüldür ki
`tui.py` yalnız tuşları buraya yönlendirsin.
"""

from __future__ import annotations

from collections.abc import Callable

from .clipboard_image import ImageChips

#: Transcript kaynağı: `show_all` → ANSI metin.
TranscriptSource = Callable[[bool], str]


class TuiExtras:
    """Transcript görünümü (Ctrl+O), görüntü yapıştırma (Ctrl+V), Option+P/T/O kancası."""

    def __init__(self) -> None:
        self.transcript_source: TranscriptSource | None = None
        self.option_handler: Callable[[str], None] | None = None
        self.image_chips: ImageChips | None = None
        #: Görünümdeki transcript metni; None = normal konuşma.
        self.view: str | None = None
        self.show_all = False
        #: Görünüme girmeden önceki kaydırma ofseti; çıkınca geri konur.
        self.saved_scroll = 0

    @property
    def viewing(self) -> bool:
        return self.view is not None

    def open(self, scroll: int) -> bool:
        if self.transcript_source is None:
            return False
        self.saved_scroll = scroll
        self.show_all = False
        self.view = self.transcript_source(False)
        return True

    def close(self) -> int:
        """Görünümden çık; geri konacak kaydırma ofsetini döndür."""
        self.view = None
        self.show_all = False
        return self.saved_scroll

    def toggle_all(self) -> None:
        """Ctrl+E (`transcript:toggleShowAll`): son mesajlar ↔ bütün konuşma."""
        if self.transcript_source is None or self.view is None:
            return
        self.show_all = not self.show_all
        self.view = self.transcript_source(self.show_all)

    def refresh(self) -> None:
        """Tur sürerken görünüm açıksa yeni mesajlar görünsün."""
        if self.transcript_source is not None and self.view is not None:
            self.view = self.transcript_source(self.show_all)

    def run_option(self, action: str) -> bool:
        if self.option_handler is None:
            return False
        self.option_handler(action)
        return True

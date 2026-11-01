"""Girdi kutusunun Claude Code düzenleme eylemleri (#194, #216).

Claude Code Chat bağlamı: `chat:externalEditor` (Ctrl+G, Ctrl+X Ctrl+E), `chat:undo`
(Ctrl+_), `chat:stash` (Ctrl+S: dolu girdiyi saklar ve temizler; boş girdide geri getirir),
`chat:clearInput` (Ctrl+L: girdi ve konuşma korunarak ekran yeniden çizilir). Satır içi
istem ve tam ekran TUI aynı fonksiyonları kullanır; ikisinde de girdi bir prompt_toolkit
`Buffer`'ıdır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer


@dataclass
class PromptStash:
    """Ctrl+S ile saklanan taslak: metin ve imleç konumu."""

    text: str = ""
    cursor: int = 0

    def toggle(self, buffer: Buffer) -> bool:
        """Dolu girdiyi sakla ve temizle; boş girdide saklananı geri getir.

        Değişiklik olduysa True döner (ekran yenilensin).
        """
        if buffer.text:
            self.text, self.cursor = buffer.text, buffer.cursor_position
            buffer.reset()
            return True
        if not self.text:
            return False
        buffer.text = self.text
        buffer.cursor_position = min(self.cursor, len(self.text))
        self.text, self.cursor = "", 0
        return True


def open_external_editor(buffer: Buffer) -> None:
    """Girdiyi `$VISUAL`/`$EDITOR` ile aç; editör kapanınca metin kutuya döner (gönderilmez)."""
    buffer.open_in_editor(validate_and_handle=False)


def undo(buffer: Buffer) -> None:
    """Son girdi düzenlemesini geri al (metin ve imleç)."""
    buffer.undo()


def redraw(app: Application[None]) -> None:
    """Ekranı tamamen yeniden çiz; girdi ve konuşma korunur."""
    renderer = getattr(app, "renderer", None)
    if renderer is not None:
        renderer.clear()
    app.invalidate()


def take_back_text(taken: list[str], draft: str) -> str:
    """Kuyruktan geri alınanlar satır satır, yazılmış taslağın ÖNÜNE konur (#190)."""
    return "\n".join([*taken, draft] if draft else taken)

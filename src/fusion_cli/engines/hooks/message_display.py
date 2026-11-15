"""`MessageDisplay` kancası (#90): görünen asistan metnini satır partileriyle dönüştürür.

Girdi (Claude Code ile aynı adlar): `turn_id`, `message_id`, `index` (mesaj içindeki parti
sırası), `final` (mesajın son partisi mi), `delta` (partinin metni). Çıktı:
`hookSpecificOutput.displayContent` partinin ekrandaki metni olur; boş metin partiyi
gizler, alan yoksa parti olduğu gibi görünür. Eşleştirici ve çıkış kodu yok sayılır;
yazılmamış süre 10 sn. Döküm, sohbet kaydı ve modelin bağlamı değişmez.

Parti sınırı satır sonudur: akan parçalar satır tamamlanana dek bekletilir; öncü beyan
(`provisional`) ile cevap metni ayrı partilerdir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...core.display_filter import Piece
from ...core.hooks.events import HookEvent
from .session import HookSession


@dataclass(slots=True)
class MessageDisplayStream:
    """Bir asistan mesajının parti akışı."""

    session: HookSession
    turn_id: str
    message_id: str
    index: int = 0
    buffer: str = ""
    provisional: bool = False

    async def feed(self, text: str, provisional: bool) -> list[Piece]:
        pieces: list[Piece] = []
        if self.buffer and provisional != self.provisional:
            pieces += await self._emit(self.buffer, final=False)
            self.buffer = ""
        self.provisional = provisional
        self.buffer += text
        cut = self.buffer.rfind("\n")
        if cut < 0:
            return pieces
        batch, self.buffer = self.buffer[: cut + 1], self.buffer[cut + 1 :]
        return pieces + await self._emit(batch, final=False)

    async def finish(self) -> list[Piece]:
        batch, self.buffer = self.buffer, ""
        if not batch and self.index == 0:
            return []
        return await self._emit(batch, final=True)

    async def _emit(self, delta: str, *, final: bool) -> list[Piece]:
        fields: dict[str, object] = {
            "turn_id": self.turn_id,
            "message_id": self.message_id,
            "index": self.index,
            "final": final,
            "delta": delta,
        }
        self.index += 1
        verdict = await self.session.emit(HookEvent.MESSAGE_DISPLAY, fields=fields)
        shown = delta if verdict.display_content is None else verdict.display_content
        return [(shown, self.provisional)] if shown else []


def display_opener(session: HookSession, turn_id: str) -> Callable[[str], MessageDisplayStream]:
    """`core.display_filter.install` için: mesaj kimliği → parti akışı."""

    def open_message(message_id: str) -> MessageDisplayStream:
        return MessageDisplayStream(session, turn_id, message_id)

    return open_message

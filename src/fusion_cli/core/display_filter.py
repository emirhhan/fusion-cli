"""Ekranda gösterilen asistan metninin süzgeci (MessageDisplay kancası, #90).

Claude Code `MessageDisplay`: asistan metni ekrana basılmadan önce satır partileri halinde
kancaya gider; `hookSpecificOutput.displayContent` yalnız GÖRÜNEN metni değiştirir, döküm
ve modelin bağlamı değişmez. Süzgeç kök tur boyunca bağlam değişkeniyle kurulur
(`engines/agent/hook_display.py`); sağlayıcı olay katmanı (`providers/eventing.py`) akan
parçaları ve motor akışsız nihai cevabı (`TurnAnswered`) buradan geçirir. Kurulu değilse
her şey eskisi gibidir. Yalnız stdlib (core katmanı).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Protocol

#: Yayınlanacak parça: (metin, öncü beyan mı).
Piece = tuple[str, bool]


class DisplayStream(Protocol):
    """Bir asistan mesajının görünen metni (satır partileriyle)."""

    async def feed(self, text: str, provisional: bool) -> list[Piece]: ...

    async def finish(self) -> list[Piece]: ...


#: Mesaj kimliği → o mesajın süzgeç akışı.
DisplayOpener = Callable[[str], DisplayStream]

_OPENER: ContextVar[DisplayOpener | None] = ContextVar("fusion_display_opener", default=None)


def install(opener: DisplayOpener) -> Token[DisplayOpener | None]:
    return _OPENER.set(opener)


def reset(token: Token[DisplayOpener | None]) -> None:
    _OPENER.reset(token)


def open_stream(message_id: str) -> DisplayStream | None:
    """Kurulu süzgecin yeni mesaj akışı; süzgeç yoksa `None` (metin olduğu gibi gider)."""
    opener = _OPENER.get()
    return opener(message_id) if opener is not None else None


async def transform(text: str) -> str:
    """Akışsız tam metni süzgeçten geçir (yoksa aynısı)."""
    stream = open_stream(f"answer-{uuid.uuid4().hex[:12]}")
    if stream is None:
        return text
    pieces = [*await stream.feed(text, False), *await stream.finish()]
    return "".join(piece for piece, _ in pieces)

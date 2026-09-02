"""Güvenilir olmayan geçmiş metnini kullanıcı/model çıktısına hazırlama."""

from __future__ import annotations

from collections.abc import Iterable

from ..core.redaction import redact
from .models import Turn


def sanitize_turn(turn: Turn) -> Turn:
    """Turn rolünü/zamanını koruyup metin içindeki sırları maskeler."""
    return Turn(role=turn.role, text=redact(turn.text), timestamp=turn.timestamp)


def sanitize_turns(turns: Iterable[Turn]) -> tuple[Turn, ...]:
    """Kaynak geçmişini tek güvenlik sınırından geçir."""
    return tuple(sanitize_turn(turn) for turn in turns)


def sanitize_title(title: str) -> str:
    """Oturum listesi başlığını da transcript metni gibi güvenli hale getir."""
    return redact(title)

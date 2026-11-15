"""Kalıcı durum oluşturmayan, ölçülmüş aktif bağlam projeksiyonu."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActiveContext:
    """Mevcut checkpoint'in sınırlı görünümü; yeniden türetilir."""

    note: str = ""
    pinned_call_ids: frozenset[str] = frozenset()
    omitted_pins: int = 0

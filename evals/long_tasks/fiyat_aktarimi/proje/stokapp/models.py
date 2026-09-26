from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Urun:
    sku: str
    ad: str
    maliyet: float
    fiyat: float
    stok: int = 0

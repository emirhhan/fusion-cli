from __future__ import annotations

import json
from pathlib import Path

from .models import Urun


class UrunDeposu:
    """Ürünleri tek bir JSON dosyasında tutar."""

    def __init__(self, yol: Path) -> None:
        self.yol = yol

    def hepsi(self) -> dict[str, Urun]:
        if not self.yol.exists():
            return {}
        ham = json.loads(self.yol.read_text(encoding="utf-8"))
        return {k: Urun(**v) for k, v in ham.items()}

    def kaydet(self, urunler: dict[str, Urun]) -> None:
        self.yol.write_text(
            json.dumps({k: vars(v) for k, v in urunler.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

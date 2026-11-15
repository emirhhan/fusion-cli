"""Beceri örnekleri scaffold token'larıyla uyumlu olmalı (Z1-19).

Ölçüldü (30 Ekim): `web-arayuz/SKILL.md` örnekleri `--gray-100`, `--gray-500` ve
`--navy` kullanıyordu; `tools/scaffold/tokens.css` bunları tanımlamıyordu. Model
örneği kopyalayınca footer zemini geçersiz kalıp beyaz yazı beyaz zeminde
görünmüyor, hover/kicker/eski fiyat renkleri düşüyordu.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src/fusion_cli"
TOKENS = SRC / "tools/scaffold/tokens.css"
KULLANAN = (
    SRC / "config/skills/web-arayuz/SKILL.md",
    SRC / "tools/scaffold/tokens.css",
    SRC / "tools/scaffold/index.html",
)


def _tanimli() -> set[str]:
    return set(re.findall(r"(--[\w-]+)\s*:", TOKENS.read_text(encoding="utf-8")))


def test_beceri_ve_iskele_yalniz_tanimli_degisken_kullanir() -> None:
    tanimli = _tanimli()
    for dosya in KULLANAN:
        kullanilan = set(re.findall(r"var\((--[\w-]+)", dosya.read_text(encoding="utf-8")))
        assert kullanilan - tanimli == set(), (dosya.name, sorted(kullanilan - tanimli))

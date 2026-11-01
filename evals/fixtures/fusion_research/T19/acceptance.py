"""Sabit dış kabul: ürün olaylarını ve temiz aday dosyalarını denetler."""

from __future__ import annotations

from pathlib import Path

from evals.research_acceptance import check_runtime


def check(root: Path, fixture: Path) -> None:
    check_runtime(root, fixture)

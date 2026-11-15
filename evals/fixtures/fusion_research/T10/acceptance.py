"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    import runpy
    from decimal import Decimal

    functions = runpy.run_path(str(workspace / "odeme/tutar.py"))
    assert functions["normalize"]("1.235") == Decimal("1.24")
    assert functions["normalize"]("2") == Decimal("2.00")
    assert functions["normalize"]("-1.235") == Decimal("-1.24")
    assert (workspace / "metin/islem.py").read_bytes() == (
        fixture / "seed" / "metin/islem.py.asset"
    ).read_bytes()

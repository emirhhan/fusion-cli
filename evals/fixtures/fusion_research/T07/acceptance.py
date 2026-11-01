"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    import runpy

    functions = runpy.run_path(str(workspace / "tarihler.py"))
    assert functions["Birinci"]().tarih(9, 2) == "02/09"
    assert functions["Ikinci"]().tarih(9, 2) == "09/02"

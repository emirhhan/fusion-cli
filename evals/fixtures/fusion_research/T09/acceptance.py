"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    import runpy
    import sys

    sys.path.insert(0, str(workspace))
    functions = runpy.run_path(str(workspace / "auth.py"))
    assert functions["giris"]("gecerli-token")
    assert not functions["giris"]("eski-token")
    assert not functions["giris"]("")
    assert (workspace / "auth.py").read_bytes() == (fixture / "seed" / "auth.py.asset").read_bytes()

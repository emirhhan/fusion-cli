"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    import runpy
    import sys

    sys.path.insert(0, str(workspace))
    functions = runpy.run_path(str(workspace / "paket/kullanim.py"))
    assert functions["oku"]("  veri ") == "veri"
    assert (workspace / "paket/ayirici.py").is_file()
    assert (workspace / "paket/kullanim.py").is_file()
    assert (workspace / "paket/ayirici.py").read_bytes() == (
        fixture / "seed" / "paket/ayirici.py.asset"
    ).read_bytes()
    assert (workspace / "paket/kullanim.py").read_bytes() == (
        fixture / "seed" / "paket/kullanim.py.asset"
    ).read_bytes()

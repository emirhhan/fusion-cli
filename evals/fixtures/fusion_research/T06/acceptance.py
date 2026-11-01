"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    import runpy

    functions = runpy.run_path(str(workspace / "ayar.py"))
    assert functions["ayar_oku"]({}) == 3
    assert functions["ayar_oku"]({"tekrar": 5}) == 5
    content = (workspace / "ayar.py").read_bytes()
    assert b"\n" not in content.replace(b"\r\n", b"")
    assert (
        content.splitlines()[3:] == (fixture / "seed/ayar.py.asset").read_bytes().splitlines()[3:]
    )
    assert (workspace / "baska.txt").read_bytes() == (
        fixture / "seed" / "baska.txt.asset"
    ).read_bytes()

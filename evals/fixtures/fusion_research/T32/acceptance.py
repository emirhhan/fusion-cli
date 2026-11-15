"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    import runpy

    first = runpy.run_path(str(workspace / "birinci.py"))
    second = runpy.run_path(str(workspace / "ikinci.py"))
    assert first["iki_kati"](3) == 6
    assert first["iki_kati"](-2) == -4
    assert second["selam"]("Ada") == "Merhaba Ada"
    document = (workspace / "README.md").read_text()
    assert "iki_kati(3) -> 6" in document
    assert "Merhaba Ada" in document

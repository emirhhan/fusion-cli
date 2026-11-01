"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    expected = "İ, ı, ş\nC:\\örnek\\mesaj\n".encode()
    assert (workspace / "mesaj.txt").read_bytes() == expected

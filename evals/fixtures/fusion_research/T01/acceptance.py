"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    assert (workspace / "notlar.txt").read_bytes() == b"literal,}"

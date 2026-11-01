"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    import runpy

    functions = runpy.run_path(str(workspace / "okuyucu.py"))
    assert functions["oku"]("a,b\n\nc,d\n") == [["a", "b"], ["c", "d"]]
    assert functions["oku"]("") == []
    assert functions["oku"]("a,b") == [["a", "b"]]
    try:
        functions["oku"]("tek")
    except ValueError as error:
        assert str(error) == "Satır iki alan içermeli"
    else:
        raise AssertionError("Hatalı satır reddedilmedi")
    assert (workspace / "cli.py").read_bytes() == (fixture / "seed" / "cli.py.asset").read_bytes()
    assert (workspace / "README.txt").read_bytes() == (
        fixture / "seed" / "README.txt.asset"
    ).read_bytes()

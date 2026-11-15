"""Sabit insan kabulünü mevcut executor'un temiz alanında çalıştırır."""

from __future__ import annotations

import re
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1 or re.fullmatch(r"T[0-9]{2}", arguments[0]) is None:
        raise ValueError("Tek bir geçerli görev kimliği gerekli.")
    fixture = Path(__file__).resolve().parent / arguments[0]
    namespace = runpy.run_path(str(fixture / "acceptance.py"))
    check = cast(Callable[[Path, Path], None], namespace["check"])
    check(Path.cwd(), fixture)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

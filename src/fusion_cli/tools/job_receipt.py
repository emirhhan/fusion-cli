"""Sarmalayıcının tamamlanma anında çağırdığı sınır betiği."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def main(arguments: list[str]) -> int:
    """Yalnız verilen iş manifestini ölç; sır veya model yapılandırması okuma."""
    if len(arguments) != 3:
        return 1
    # Doğrudan betik çağrısı: kurulu paketle aynı kaynak kökünü import et.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from fusion_cli.tools.job_delivery import save_completion
    from fusion_cli.tools.jobs import _JOB_ID, JOBS_DIR

    root = Path(arguments[0])
    if not _JOB_ID.fullmatch(arguments[1]):
        return 1
    try:
        save_completion(root / JOBS_DIR, root, arguments[1], int(arguments[2]))
    except (OSError, ValueError):
        logging.getLogger(__name__).exception("İş tamamlanma receipt'i üretilemedi")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

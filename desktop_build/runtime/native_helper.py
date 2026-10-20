"""Paketli macOS masaüstü yardımcısını depodaki Swift kaynağından üretir."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HELPER_BUILD_TIMEOUT_S = 60
HELPER_NAME = "fusion-desktop-host"


def build_native_helper(repo_root: str, work_directory: str) -> str | None:
    """Derleme makinesinde üret; kullanıcı bilgisayarında Swift gerekmez."""
    if sys.platform != "darwin":
        return None
    source = Path(repo_root) / "src/fusion_cli/tools/data/desktop_host.swift"
    destination = Path(work_directory) / "native-desktop" / HELPER_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["/usr/bin/swiftc", str(source), "-o", str(destination)],
        capture_output=True,
        text=True,
        timeout=HELPER_BUILD_TIMEOUT_S,
        check=True,
    )
    destination.chmod(0o755)
    return str(destination)

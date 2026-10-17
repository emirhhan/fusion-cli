"""PWA uçtan uca kabul: gerçek ASGI sunucusu + gerçek Chromium, 375 ve 430 px (Playwright)."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT = ROOT / "app/node_modules/playwright/index.mjs"
NODE = shutil.which("node") or "/opt/homebrew/opt/node@22/bin/node"
CHROMIUM = list(Path.home().glob("Library/Caches/ms-playwright/chromium-*")) + list(
    Path.home().glob(".cache/ms-playwright/chromium-*")
)

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_file() and Path(NODE).exists() and CHROMIUM),
    reason="playwright/chromium kurulu değil",
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_telefon_boyutunda_uctan_uca_akis(tmp_path: Path) -> None:
    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, str(ROOT / "tests/e2e/pwa_server.py"), str(port)],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert server.stdout is not None and server.stdout.readline().strip() == "HAZIR"
        done = subprocess.run(
            [
                NODE,
                str(ROOT / "tests/e2e/pwa_e2e.mjs"),
                f"http://127.0.0.1:{port}",
                str(tmp_path / "shots"),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        lines = done.stdout.strip().splitlines()
        assert sum(line.startswith("375px ✓") for line in lines) == 12
        assert sum(line.startswith("430px ✓") for line in lines) == 12
    finally:
        server.terminate()
        server.wait(timeout=10)

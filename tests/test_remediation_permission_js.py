"""İzin ve bağlantı denetleyicilerini sahte dış sınırlarla gerçek Node kodunda çalıştır."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or "/opt/homebrew/opt/node@22/bin/node"


@pytest.mark.parametrize(
    "script",
    [
        "chrome_permission_view_unit.mjs",
        "chrome_permission_wait_unit.mjs",
        "chrome_permission_transport_unit.mjs",
        "chrome_permission_navigation_unit.mjs",
        "chrome_panel_connection_unit.mjs",
    ],
)
@pytest.mark.skipif(not Path(NODE).exists(), reason="Node kurulu değil")
def test_permission_runtime_contract(script):
    result = subprocess.run(
        [NODE, str(ROOT / "tests" / "e2e" / script)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr

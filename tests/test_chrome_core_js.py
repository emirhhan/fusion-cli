"""Eklenti çekirdeğinin (`chrome-extension/core.js`) tarayıcı API'li parçaları Node'da sınanır.

İzleyici kaydı (`registerMonitor`), sekme grubu ve yeni pencere denetimleri sahte `chrome`
nesnesiyle denenir. Node yoksa atlanır.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or "/opt/homebrew/opt/node@22/bin/node"

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node kurulu değil")


def test_izleyici_kaydi_serilesir_all_urls_kurmaz_sekme_grubu_ve_pencere_denetlenir() -> None:
    done = subprocess.run(
        [NODE, str(ROOT / "tests/e2e/chrome_core_unit.mjs")],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "chrome-core ✓" in done.stdout

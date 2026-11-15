"""Eklentinin ekran kaydedicisi (`chrome-extension/recorder.js`) Node'da sınanır (P-044).

Kareleri uzun yaşayan belge toplar; başlat/durdur/parça parça çekme ve hata yolları
sahte kare kaynağıyla denenir. Node yoksa atlanır.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or "/opt/homebrew/opt/node@22/bin/node"

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node kurulu değil")


def test_kaydedici_baslat_durdur_ve_parca_parca_cekme() -> None:
    done = subprocess.run(
        [NODE, str(ROOT / "tests/e2e/chrome_recorder_unit.mjs")],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "chrome-recorder ✓" in done.stdout

"""Eklentinin sayfa çekirdeği gerçek Chromium'da: eski sayfa ref'i yeni sayfaya tıklamaz (WP09).

Eklenti ref'leri belge başına sıfırlanan bir diziden (`e0`, `e1`, …) üretir. Sayfa
değişince eski `e0` yeni sayfada başka bir düğmeye denk gelebiliyordu. Artık her
belge bir kimlik taşır; komut başka belgenin kimliğiyle gelirse reddedilir.
"""

from __future__ import annotations

import subprocess

import pytest

from .test_remote_pwa_e2e import CHROMIUM, NODE, PLAYWRIGHT, ROOT

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_file() and CHROMIUM), reason="playwright/chromium kurulu değil"
)


def test_eski_sayfanin_refi_yeni_sayfada_tiklamaz() -> None:
    done = subprocess.run(
        [NODE, str(ROOT / "tests/e2e/chrome_refs_e2e.mjs")],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "chrome-refs ✓" in done.stdout

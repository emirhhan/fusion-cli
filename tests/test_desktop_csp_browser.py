"""Derlenmiş masaüstü arayüzü üretim CSP'siyle gerçek Chromium'da ihlal üretmez (R2-04).

`app/dist` (npm run build) varsa çalışır: paketle gelen script, stil, font ve görseller
üretim CSP'si altında engelleniyorsa ihlal listesi boş olmaz.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from .test_remote_pwa_e2e import CHROMIUM, NODE, PLAYWRIGHT, ROOT

_DIST = ROOT / "app" / "dist" / "index.html"

pytestmark = pytest.mark.skipif(
    not (PLAYWRIGHT.is_file() and CHROMIUM and _DIST.is_file()),
    reason="playwright/chromium ya da app/dist yok",
)


def test_uretim_csp_derlenmis_arayuzu_engellemez(tmp_path) -> None:
    done = subprocess.run(
        [
            NODE,
            str(ROOT / "tests/e2e/desktop_csp_e2e.mjs"),
            str(ROOT / "app" / "dist"),
            str(tmp_path / "csp.png"),
            str(ROOT / "app" / "src-tauri" / "tauri.conf.json"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    sonuc = json.loads(done.stdout.strip().splitlines()[-1])
    assert sonuc["violations"] == [], sonuc
    assert sonuc["fonts"] >= 1

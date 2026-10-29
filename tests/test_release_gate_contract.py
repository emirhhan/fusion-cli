"""Masaüstü sürümü Python kalite kapısı geçmeden yayımlanmaz (Q1-01, WP19).

Ölçüldü (28 Ekim): `desktop.yml` içindeki `release` işi yalnız paket işlerine
(`macos`, `windows`, `terminal`) bağlıydı; lint/tip/test kapısı ayrı `ci.yml`'de
koştuğu için testler kırmızıyken etiket atılsa da herkese açık Release oluşuyordu.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _yukle(ad: str) -> dict:
    veri = yaml.safe_load((_WORKFLOWS / ad).read_text(encoding="utf-8"))
    # PyYAML `on:` anahtarını True olarak okur.
    if True in veri:
        veri["on"] = veri.pop(True)
    return veri


def test_ci_yeniden_kullanilabilir_kalite_kapisidir():
    ci = _yukle("ci.yml")

    assert "workflow_call" in ci["on"]
    assert any("make check" in str(step.get("run", "")) for step in ci["jobs"]["check"]["steps"])


def test_surum_isi_kalite_kapisina_baglidir():
    desktop = _yukle("desktop.yml")
    jobs = desktop["jobs"]
    kapi = next(
        name for name, job in jobs.items() if job.get("uses") == "./.github/workflows/ci.yml"
    )

    assert kapi in jobs["release"]["needs"]
    assert {"macos", "windows", "terminal"} <= set(jobs["release"]["needs"])

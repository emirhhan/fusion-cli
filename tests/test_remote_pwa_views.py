"""PWA görünümleri (jsdom): yeniden çizim girdiyi silmez, onay kartı düğmesiz kalmaz."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWA = ROOT / "src/fusion_cli/remote/pwa"
JSDOM = ROOT / "app/node_modules/jsdom/lib/api.js"
NODE = shutil.which("node") or "/opt/homebrew/opt/node@22/bin/node"
pytestmark = pytest.mark.skipif(
    not Path(NODE).exists() or not JSDOM.exists(), reason="node ya da jsdom yok"
)


@pytest.fixture(scope="module")
def result() -> dict[str, Any]:
    done = subprocess.run(
        [NODE, str(Path(__file__).with_name("pwa_dom_harness.mjs")), str(PWA), str(JSDOM)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    parsed: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return parsed


def test_yeniden_cizim_yeni_proje_adini_ve_formu_korur(result: dict[str, Any]) -> None:
    # Ölçüldü (30 Ekim): renderChats formu her çizimde yeniden kuruyor, yazılan ad siliniyordu.
    assert result["draft"] == {"value": "Yeni oyun", "formHidden": False, "focused": True}


def test_onay_kartinda_nesne_argumanlari_gizlenmez(result: dict[str, Any]) -> None:
    # Ölçüldü (30 Ekim): `args.length` nesnede undefined; kullanıcı neyi onayladığını göremiyordu.
    assert result["argsObject"]["details"] is True
    assert "a.txt" in result["argsObject"]["text"]


def test_taninmayan_secenekte_reddet_daima_vardir(result: dict[str, Any]) -> None:
    # Ölçüldü (30 Ekim): tanınmayan seçenek kartı düğmesiz bırakıyor, görev sonsuza dek bekliyordu.
    assert result["unknownOptions"]["buttons"] == ["Reddet"]
    assert result["unknownOptions"]["note"] is True
    assert result["onceOnly"] == ["Bir kez izin ver", "Reddet"]


def test_tehlike_ve_neden_birlikte_gosterilir(result: dict[str, Any]) -> None:
    assert result["both"] is True

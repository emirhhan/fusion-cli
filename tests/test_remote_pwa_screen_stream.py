"""PWA canlı ekran akışı: ağ kopması, oturum bitişi, arka plan ve kullanıcı durdurması (Node'da)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

PWA = Path(__file__).resolve().parents[1] / "src/fusion_cli/remote/pwa"
NODE = shutil.which("node") or "/opt/homebrew/opt/node@22/bin/node"
pytestmark = pytest.mark.skipif(
    not Path(NODE).exists() and shutil.which("node") is None, reason="node yok"
)

HARNESS = Path(__file__).with_name("screen_stream_harness.mjs")


@pytest.fixture(scope="module")
def result() -> dict[str, Any]:
    done = subprocess.run(
        [NODE, str(HARNESS), str(PWA / "screen-stream.js")],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    parsed: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return parsed


def test_ag_kopunca_ustel_beklemeyle_kendiliginden_geri_gelir(result: dict[str, Any]) -> None:
    network = result["network"]
    assert network["retries"][:3] == [1000, 2000, 4000]
    assert "reconnecting" in network["states"] and network["states"][-1] == "live"
    assert network["frames"] >= 2 and network["maxInflight"] == 1


def test_oturum_bitince_kendiliginden_yeni_onay_istemez(result: dict[str, Any]) -> None:
    expiry = result["expiry"]
    assert expiry["calls"].count("screen.request") == 0
    assert expiry["renewed"] is False
    assert expiry["states"][-1] == "ended"


def test_kullanici_durdurunca_yenileme_istenmez(result: dict[str, Any]) -> None:
    assert result["stop"]["stopCalled"] is True and result["stop"]["requests"] == 0


def test_arka_planda_istek_yok_gorununce_surer(result: dict[str, Any]) -> None:
    hidden = result["hidden"]
    assert hidden["whileHidden"] == 0 and hidden["paused"] and hidden["afterVisible"]


def test_kimlik_gecersizse_akis_durur(result: dict[str, Any]) -> None:
    assert result["auth"]["states"][-1] == "auth"


def test_yenilemeden_sonra_etkin_oturum_sorulmadan_surer(result: dict[str, Any]) -> None:
    reload = result["reload"]
    assert reload["resumedAsked"] is False and reload["idleAsked"] is False
    assert reload["idleStates"][-1] == "idle"

"""PWA RPC istemcisi: sıralı istek, geçici 401'de yeniden deneme, eşleşmeyi yalnız iptalde silme."""

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


@pytest.fixture(scope="module")
def result() -> dict[str, Any]:
    done = subprocess.run(
        [NODE, str(Path(__file__).with_name("api_harness.mjs")), str(PWA)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    parsed: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return parsed


def test_eszamanli_cagrilar_sirayla_gider(result: dict[str, Any]) -> None:
    serial = result["serial"]
    assert serial["max"] == 1 and serial["strictlyIncreasing"] and serial["count"] == 8


def test_eski_sira_bir_kez_yeniden_denenir(result: dict[str, Any]) -> None:
    assert result["retry"] == {"calls": 2, "ok": True}


def test_yalniz_cihaz_iptali_eslesmeyi_siler(result: dict[str, Any]) -> None:
    assert result["cihaz_iptal"]["auth"] is True
    for reason in ("imza_gecersiz", "zaman_asimi", "sira_eski"):
        assert result[reason]["auth"] is False, reason
    assert "saat" in result["zaman_asimi"]["message"]


def test_hata_kuyrugu_tikamaz(result: dict[str, Any]) -> None:
    assert result["queue"] == {"first": "ag", "second": True}


def test_onay_ve_sohbet_olaylari_liste_kuyrugunun_onune_gecer(result: dict[str, Any]) -> None:
    assert result["priority"] == [
        "initial",
        "approvals.respond",
        "tasks.events",
        "projects.list",
        "schedules.list",
    ]

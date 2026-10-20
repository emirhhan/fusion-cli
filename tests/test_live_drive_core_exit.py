"""Canlı sürücü: ölen çekirdek süre dolana kadar beklenmez, olaylar satır satır yazılır."""

from __future__ import annotations

import argparse
import sys
import time

from evals import live_drive

#: Oturumu açan, bir olay yayan ve tur isteği gelince cevap vermeden çıkan sahte çekirdek.
_FAKE_CORE = """
import json, sys
for line in sys.stdin:
    istek = json.loads(line)
    if istek["ad"] == "oturum.baslat":
        print(json.dumps({"tip": "sonuc", "id": istek["id"], "veri": {"ok": True}}), flush=True)
    else:
        olay = {"tip": "olay", "veri": {"olay": "ToolStarted", "name": "play_probe"}}
        print(json.dumps(olay), flush=True)
        sys.exit(3)
"""


async def test_olen_cekirdek_turu_hemen_bitirir_ve_son_olay_diskte_kalir(tmp_path, monkeypatch):
    monkeypatch.setattr(live_drive, "_komut", lambda _args: [sys.executable, "-c", _FAKE_CORE])
    args = argparse.Namespace(
        kok=str(tmp_path), mod="auto", gorev=["oyun yap"], sure=120.0, chrome="", onay="once"
    )
    events = tmp_path / "olaylar.jsonl"

    started = time.monotonic()
    with events.open("wb") as log:
        record = await live_drive.drive(args, None, log)
        flushed = events.read_text(encoding="utf-8")

    assert time.monotonic() - started < 30
    assert record["turlar"][0]["ok"] is False
    assert "çekirdek kapandı" in record["turlar"][0]["metin"]
    assert "play_probe" in flushed
    import json

    assert isinstance(json.loads(flushed.splitlines()[0])["ts"], float)

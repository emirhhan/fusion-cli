"""stdio döngüsü: satır girdi → satır çıktı."""

from __future__ import annotations

import json

from fusion_cli.appserver.server import serve


async def _run(satirlar_girdi, tmp_path):
    cikti: list[str] = []

    async def _reader():
        for satir in satirlar_girdi:
            yield satir

    await serve(_reader(), cikti.append, root=tmp_path, home=tmp_path / "ev")
    return cikti


async def test_istek_sonuc_uretir(tmp_path):
    girdi = [json.dumps({"tip": "istek", "id": "1", "ad": "oturum.durum", "veri": {}})]

    cikti = await _run(girdi, tmp_path)

    sonuc = json.loads(cikti[-1])
    assert sonuc["tip"] == "sonuc" and sonuc["id"] == "1"


async def test_bozuk_satir_sureci_dusurmez(tmp_path):
    girdi = [
        "{bozuk json",
        json.dumps({"tip": "istek", "id": "2", "ad": "oturum.durum", "veri": {}}),
    ]

    cikti = await _run(girdi, tmp_path)

    hatalar = [json.loads(s) for s in cikti if json.loads(s).get("tip") == "olay"]
    assert any(h["veri"]["olay"] == "ProtocolError" for h in hatalar)
    assert any(json.loads(s).get("id") == "2" for s in cikti)


async def test_eslesmeyen_cevap_hata_olayi_uretir(tmp_path):
    girdi = [json.dumps({"tip": "cevap", "id": "yok", "veri": {}})]

    cikti = await _run(girdi, tmp_path)

    assert any(json.loads(s)["veri"].get("olay") == "ProtocolError" for s in cikti)


async def test_akis_bitince_duzgun_kapanir(tmp_path):
    """stdin kapanınca döngü biter; istisna fırlamaz."""
    cikti = await _run([], tmp_path)

    assert cikti == []

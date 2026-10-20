"""stdio döngüsü: satır girdi → satır çıktı."""

from __future__ import annotations

import asyncio
import json

from fusion_cli.appserver.server import serve
from fusion_cli.appserver.session import AppSession


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


async def test_uzun_istek_islenirken_sonraki_satir_okunur(tmp_path, monkeypatch):
    """`serve` bir istek işlerken tıkanmamalı — sıradaki satırı hemen okumalı.

    Bu test, `async for line in lines: await session.handle(message)`
    biçiminde geri alınırsa (arka plana almadan) TIMEOUT ile kırmızıya
    düşecek şekilde kurulmuştur: uzun süren istek bitmeden ikinci satırın
    işlenip işlenmediğini sınırlı bir bekleme ile denetler.
    """
    processing_started = asyncio.Event()
    release_processing = asyncio.Event()
    original_handle = AppSession.handle

    async def yavas_handle(self, request):
        if request.id == "uzun":
            processing_started.set()
            await release_processing.wait()
        await original_handle(self, request)

    monkeypatch.setattr(AppSession, "handle", yavas_handle)

    girdi_kuyrugu: asyncio.Queue[str | None] = asyncio.Queue()

    async def _kuyruktan_oku():
        while True:
            satir = await girdi_kuyrugu.get()
            if satir is None:
                return
            yield satir

    cikti: list[str] = []
    hizli_geldi = asyncio.Event()

    def _yaz(satir: str) -> None:
        cikti.append(satir)
        if json.loads(satir).get("id") == "hizli":
            hizli_geldi.set()

    serve_gorevi = asyncio.ensure_future(
        serve(_kuyruktan_oku(), _yaz, root=tmp_path, home=tmp_path / "ev")
    )

    await girdi_kuyrugu.put(
        json.dumps({"tip": "istek", "id": "uzun", "ad": "oturum.durum", "veri": {}})
    )
    await asyncio.wait_for(processing_started.wait(), timeout=1.0)

    await girdi_kuyrugu.put(
        json.dumps({"tip": "istek", "id": "hizli", "ad": "oturum.durum", "veri": {}})
    )

    # Düzeltme geri alınırsa döngü hâlâ "uzun" isteğinde tıkalı kalır ve
    # bu bekleme zaman aşımına uğrar — kırmızı koşuda gördüğümüz budur.
    await asyncio.wait_for(hizli_geldi.wait(), timeout=1.0)

    release_processing.set()
    await girdi_kuyrugu.put(None)
    await asyncio.wait_for(serve_gorevi, timeout=1.0)

    assert any(json.loads(s).get("id") == "uzun" for s in cikti)
    assert any(json.loads(s).get("id") == "hizli" for s in cikti)


async def test_bilinmeyen_istisna_hata_olayi_olarak_bildirilir(tmp_path, monkeypatch):
    """Arka plan görevi beklenmedik bir istisna fırlatırsa sessizce yutulmaz."""

    async def patlayan_handle(self, request):
        raise RuntimeError("beklenmeyen hata")

    monkeypatch.setattr(AppSession, "handle", patlayan_handle)

    girdi = [json.dumps({"tip": "istek", "id": "1", "ad": "oturum.durum", "veri": {}})]

    cikti = await _run(girdi, tmp_path)

    hatalar = [json.loads(s) for s in cikti if json.loads(s).get("tip") == "olay"]
    assert any("beklenmeyen hata" in h["veri"].get("mesaj", "") for h in hatalar)

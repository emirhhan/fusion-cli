"""Görsel işinin girdi anlık görüntüsü ve eksik referansın makine okunur reddi.

Ölçüldü (29 Ekim): iş kabul edilirken istem/sağlayıcı/oran yerel sözlüğe,
referans görsel ise baytlarıyla sabitleniyor; sonradan dosya değişse de
sağlayıcı kabul anındaki baytları okuyor (`test_appserver_session.py`
referans anlık görüntüsü testi). Kusur: eksik/bozuk referans reddi yalnız
serbest metin taşıyordu; arayüz üst düğümün çıktısının silindiğini
anlayamıyordu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.appserver import image_create
from fusion_cli.appserver import session as module
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from tests.test_image_create_flow import _config


async def test_eksik_referans_kodlu_reddedilir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(image_create, "image_output_dir", lambda: tmp_path)
    sonuc = await image_create.create_image(
        _config("gemini_web/main/auto"),
        {"istem": "x", "islem": "duzenle", "referans": str(tmp_path / "silindi.png")},
        environ={},
    )
    assert sonuc["ok"] is False
    assert sonuc["code"] == "reference_invalid"


async def test_kalici_is_eksik_referansi_kabul_oncesi_kodlu_reddeder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(module, "image_output_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "image_providers", lambda *a, **kw: [{"deger": "offline"}])
    session = AppSession([].append, root=tmp_path, home=tmp_path / "ev")
    try:
        sonuc = await session._dispatch(
            Request(
                "r",
                "gorsel.is.baslat",
                {"requestId": "job-1", "istem": "x", "referans": str(Path(tmp_path) / "yok.png")},
            )
        )
        assert sonuc["ok"] is False and sonuc["code"] == "reference_invalid"
        listed = await session._dispatch(Request("l", "gorsel.is.liste", {}))
        assert listed["isler"] == []
    finally:
        await session.close()


@pytest.mark.parametrize("alan", ["istem", "oran"])
async def test_baslangic_sonrasi_degisen_istek_calisan_isi_etkilemez(
    tmp_path, monkeypatch, alan
) -> None:
    """İstek sözlüğü kabul anında kopyalanır; arayüzün sonradan değişen taslağı işe sızmaz."""
    import asyncio

    monkeypatch.setattr(module, "image_output_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "image_providers", lambda *a, **kw: [{"deger": "offline"}])
    görülen: list[dict[str, object]] = []
    girdi, serbest, tuketildi = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def render(config, data, **kwargs):
        girdi.set()
        await serbest.wait()
        görülen.append(dict(data))
        tuketildi.set()
        return {"ok": False}

    monkeypatch.setattr(module, "create_image", render)
    session = AppSession([].append, root=tmp_path, home=tmp_path / "ev")
    veri = {"requestId": "snap-1", "istem": "dağ", "oran": "16:9", "saglayici": "offline"}
    try:
        await session._dispatch(Request("s", "gorsel.is.baslat", veri))
        await girdi.wait()
        veri[alan] = "değişti"  # çağıranın sözlüğü iş başladıktan sonra değişir
        serbest.set()
        await asyncio.wait_for(tuketildi.wait(), 3)
        assert görülen[0]["istem"] == "dağ" and görülen[0]["oran"] == "16:9"
    finally:
        serbest.set()
        await session.close()

"""Oturum ömrü ve istek yönlendirme."""

from __future__ import annotations

import asyncio
import json

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


def _session(tmp_path, satirlar):
    return AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")


async def test_bilinmeyen_istek_hata_sonucu_doner(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="1", name="olmayan.istek", data={}))

    sonuc = json.loads(satirlar[-1])
    assert sonuc["tip"] == "sonuc"
    assert sonuc["id"] == "1"
    assert sonuc["veri"]["ok"] is False


async def test_durum_istegi_kok_dizini_bildirir(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="2", name="oturum.durum", data={}))

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is True
    assert veri["kok"] == str(tmp_path)


async def test_komut_listesi_doner(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="3", name="komut.listele", data={}))

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is True
    assert any(k["ad"] == "help" for k in veri["komutlar"])


async def test_eslesmeyen_cevap_false_doner(tmp_path):
    from fusion_cli.appserver.protocol import Reply

    oturum = _session(tmp_path, [])

    assert oturum.resolve_reply(Reply(id="yok", data={})) is False


async def test_kapanista_bekleyen_sorular_serbest_birakilir(tmp_path):
    """Kapanış bekleyen soruyu sonsuza dek asılı bırakmamalı."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    _kimlik, gelecek = oturum.pending.new_question()

    await oturum.close()
    await asyncio.sleep(0)

    assert gelecek.done()

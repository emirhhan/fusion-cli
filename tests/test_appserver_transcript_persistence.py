"""Duraklayan tur da geçmişe yazılmalı; soru kalıp cevap kaybolmamalı.

Ölçüldü (7 Eylül, kullanıcının Godot koşuları): plan adımları duraklayınca tur
`ok=False` döndü. Soru transcript'e yazıldı, cevap yazılmadı — kullanıcının
diskindeki `198b3a19…` sohbeti 8 soru ve 0 cevap taşıyor. Sekme yeniden
açıldığında model kendi ne dediğini göremiyor ve kaldığı yerden süremiyor.

Transcript bir BAŞARI kaydı değil, NE OLDUĞU kaydıdır: duraklama da bir cevaptır.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.transcript_store import load_transcript_messages

pytestmark = pytest.mark.asyncio


def _session(tmp_path, satirlar):
    return AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")


def _sonuc(satirlar, kimlik):
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(f"kimlik için sonuç bulunamadı: {kimlik}")


def _sahte_sonuc(monkeypatch, *, ok, metin):
    from types import SimpleNamespace

    async def _calistir(*_args, **_kwargs):
        return SimpleNamespace(ok=ok, final_text=metin, messages=())

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _calistir)


async def _tur(oturum, satirlar, gorev):
    await oturum.handle(Request(id="t", name="tur.calistir", data={"gorev": gorev}))
    return _sonuc(satirlar, "t")


def _kayitli(oturum, tmp_path):
    return [
        (mesaj.role, mesaj.content)
        for mesaj in load_transcript_messages(
            oturum._state.config.memory_dir, tmp_path, conversation_id="sekme"
        )
    ]


async def _sekme(oturum):
    await oturum.handle(Request(id="b", name="oturum.baslat", data={"sohbet_id": "sekme"}))


async def test_duraklayan_turun_cevabi_da_kaydedilir(tmp_path, monkeypatch):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)
    _sahte_sonuc(monkeypatch, ok=False, metin="Plan adımı duraklatıldı: asset-acquisition.")

    await _tur(oturum, satirlar, "oyun yap")

    assert _kayitli(oturum, tmp_path) == [
        ("user", "oyun yap"),
        ("assistant", "Plan adımı duraklatıldı: asset-acquisition."),
    ]


async def test_basarili_turun_cevabi_kaydedilmeye_devam_eder(tmp_path, monkeypatch):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)
    _sahte_sonuc(monkeypatch, ok=True, metin="bitti")

    await _tur(oturum, satirlar, "oyun yap")

    assert _kayitli(oturum, tmp_path) == [("user", "oyun yap"), ("assistant", "bitti")]


async def test_bos_cevap_kaydedilmez(tmp_path, monkeypatch):
    """Boş satır geçmişi kirletir ve modele hiçbir şey söylemez."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)
    _sahte_sonuc(monkeypatch, ok=False, metin="   ")

    await _tur(oturum, satirlar, "oyun yap")

    assert _kayitli(oturum, tmp_path) == [("user", "oyun yap")]


async def test_iptal_edilen_tur_da_iz_birakir(tmp_path, monkeypatch):
    """İptal de bir cevaptır: soru cevapsız kalırsa devam etmek imkânsızdır."""
    import asyncio

    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)

    async def _bekle(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _bekle)
    tur = asyncio.ensure_future(_tur(oturum, satirlar, "oyun yap"))
    await asyncio.sleep(0)
    await oturum.handle(Request(id="k", name="tur.kes", data={}))
    await tur

    roller = [rol for rol, _ in _kayitli(oturum, tmp_path)]
    assert roller == ["user", "assistant"]

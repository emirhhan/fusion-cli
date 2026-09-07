"""Diskteki sohbetler listelenebilmeli; ulaşılamayan geçmiş yok sayılmış geçmiştir.

Ölçüldü (kullanıcının diski, 8 Eylül): 110 sohbet transcript dosyalarında duruyor
ama arayüz yalnız AÇIK sekmeleri gösteriyordu. Kullanıcı dünkü konuşmasına
ulaşamadığı için her seferinde sıfırdan anlatmak zorunda kaldı.

Liste bir ARAMA sonucu değil, bir kapıdır: kimlik, başlık ve zaman yeter.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.transcript_store import TranscriptStore, list_conversations


def _yaz(memory, root, sohbet, sorular, cevaplar=()):
    store = TranscriptStore(memory, root, conversation_id=sohbet)
    for soru in sorular:
        store.record_user(soru)
    for cevap in cevaplar:
        store.record_assistant(cevap)


def test_sohbetler_kimlik_baslik_ve_zamanla_listelenir(tmp_path):
    memory, root = tmp_path / "bellek", tmp_path / "proje"
    root.mkdir()
    _yaz(memory, root, "sekme-a", ["oyun yaz", "devam et"], ["tamam"])

    sohbetler = list_conversations(memory, root)

    assert len(sohbetler) == 1
    assert sohbetler[0].conversation_id == "sekme-a"
    assert sohbetler[0].title == "oyun yaz"
    assert sohbetler[0].message_count == 3
    assert sohbetler[0].updated_at > 0


def test_en_son_konusan_sohbet_basta_gelir(tmp_path):
    memory, root = tmp_path / "bellek", tmp_path / "proje"
    root.mkdir()
    _yaz(memory, root, "eski", ["ilk"])
    _yaz(memory, root, "yeni", ["ikinci"])

    assert [item.conversation_id for item in list_conversations(memory, root)] == ["yeni", "eski"]


def test_kullanici_mesaji_olmayan_sohbet_listelenmez(tmp_path):
    """Yalnız araç olayı taşıyan kayıt kullanıcı için bir sohbet değildir."""
    memory, root = tmp_path / "bellek", tmp_path / "proje"
    root.mkdir()
    _yaz(memory, root, "bos", [], ["yalnız cevap"])

    assert list_conversations(memory, root) == ()


def test_baslik_uzun_mesajda_kirpilir(tmp_path):
    memory, root = tmp_path / "bellek", tmp_path / "proje"
    root.mkdir()
    _yaz(memory, root, "sekme", ["x" * 300])

    assert len(list_conversations(memory, root)[0].title) <= 80


@pytest.mark.asyncio
async def test_protokol_sohbetleri_dondurur(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    _yaz(oturum._state.config.memory_dir, tmp_path, "sekme-a", ["oyun yaz"])

    await oturum.handle(Request(id="1", name="sohbet.listele", data={}))

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is True
    assert [item["sohbet_id"] for item in veri["sohbetler"]] == ["sekme-a"]
    assert veri["sohbetler"][0]["baslik"] == "oyun yaz"

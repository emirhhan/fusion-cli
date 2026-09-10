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


def test_silinen_sohbet_liste_ve_baglama_geri_donmez(tmp_path):
    from fusion_cli.cli.repl.transcript_store import delete_conversation, load_transcript_messages

    memory, root = tmp_path / "bellek", tmp_path / "proje"
    store = TranscriptStore(memory, root, conversation_id="silinen")
    store.record_user("sil")
    _yaz(memory, root, "kalan", ["koru"])
    other = tmp_path / "diger"
    _yaz(memory, other, "silinen", ["diger proje"])

    delete_conversation(memory, root, "silinen")
    delete_conversation(memory, root, "silinen")
    store.record_assistant("iptal sonrasi gec gelen cevap")
    # Silmeyle yarışan başka süreç önceden hazırladığı olayı yazmış olabilir.
    with store.events_path.open("a") as handle:
        handle.write(
            json.dumps({"session_id": "silinen", "event": "UserMessage", "text": "gec"}) + "\n"
        )

    assert [row.conversation_id for row in list_conversations(memory, root)] == ["kalan"]
    assert load_transcript_messages(memory, root, conversation_id="silinen") == []
    assert [row.content for row in load_transcript_messages(memory, root)] == ["koru"]
    assert len(list_conversations(memory, other)) == 1


@pytest.mark.asyncio
async def test_silme_protokolu_aktif_turu_iptal_eder_ve_gecmisi_temizler(tmp_path):
    import asyncio

    output = []
    session = AppSession(output.append, root=tmp_path, home=tmp_path / "ev")
    await session.handle(Request(id="start", name="oturum.baslat", data={"sohbet_id": "aktif"}))
    session._transcript_store.record_user("mesaj")
    session._rebind_transcript()
    started = asyncio.Event()

    async def late_answer():
        started.set()
        try:
            await asyncio.Future()
        finally:
            session._transcript_store.record_assistant("iptal cevabi")

    session._turn = asyncio.create_task(late_answer())
    await started.wait()
    await session.handle(Request(id="delete", name="sohbet.sil", data={"sohbet_id": "aktif"}))
    assert json.loads(output[-1])["veri"]["ok"] is True
    with pytest.raises(asyncio.CancelledError):
        await session._turn
    assert session._state.history == []
    assert list_conversations(session._state.config.memory_dir, tmp_path) == ()


@pytest.mark.asyncio
async def test_silme_protokolu_baska_proje_ve_gecersiz_kimlik(tmp_path):
    output = []
    session = AppSession(output.append, root=tmp_path, home=tmp_path / "ev")
    other = tmp_path / "diger"
    _yaz(session._state.config.memory_dir, other, "eski", ["eski mesaj"])
    await session.handle(Request(id="bad", name="sohbet.sil", data={"sohbet_id": " "}))
    assert json.loads(output[-1])["veri"]["ok"] is False
    await session.handle(
        Request(id="ok", name="sohbet.sil", data={"sohbet_id": "eski", "kok": str(other)})
    )
    assert json.loads(output[-1])["veri"]["ok"] is True
    assert list_conversations(session._state.config.memory_dir, other) == ()


@pytest.mark.asyncio
async def test_silme_yazma_hatasini_basari_gibi_gostermez(tmp_path, monkeypatch):
    from fusion_cli.appserver import session as session_module

    output = []
    session = AppSession(output.append, root=tmp_path, home=tmp_path / "ev")
    _yaz(session._state.config.memory_dir, tmp_path, "korunan", ["mesaj"])

    def fail_delete(*_args):
        raise OSError("Silme kaydı yazılamadı")

    monkeypatch.setattr(session_module, "delete_conversation", fail_delete)
    await session.handle(Request(id="delete", name="sohbet.sil", data={"sohbet_id": "korunan"}))
    assert json.loads(output[-1])["veri"]["ok"] is False
    assert len(list_conversations(session._state.config.memory_dir, tmp_path)) == 1

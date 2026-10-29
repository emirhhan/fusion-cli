"""Bellek koruyucusu: sessiz kapanma, yalan başarı ve sızan Chroma hataları (M1-30/31/32).

Ölçüldü (29 Ekim): (1) tek koleksiyonun zaman aşımı dizindeki TÜM koleksiyonları (ders,
performans, kod indeksi) oturum boyunca kapatıyordu; (2) kilit/zaman aşımında yazma
sessizce `None` dönüyor, `lessons.add` True, `reindex` "added=N" diyordu; (3) Chroma'nın
kendi istisnaları (boyut uyuşmazlığı vb.) çağırana aynen fırlıyordu. Gerçek Chroma yok:
sahte koleksiyonlarla, ağsız ve hızlı.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from fusion_cli.core.memory import Lesson, LessonKind
from fusion_cli.memory import code_index, lessons, store


class _Koleksiyon:
    def __init__(self, ad: str = "dersler") -> None:
        self.name = ad
        self.eklenen: list[str] = []
        self.hata: Exception | None = None
        self.bekle = 0.0
        self.engel: threading.Event | None = None

    def add(self, ids, documents=None, metadatas=None):
        if self.hata:
            raise self.hata
        if self.bekle:
            time.sleep(self.bekle)
        self.eklenen.extend(ids)

    def update(self, ids, documents=None, metadatas=None):
        if self.hata:
            raise self.hata

    def delete(self, ids):
        if self.hata:
            raise self.hata

    def query(self, query_texts, n_results=1):
        if self.engel is not None:
            self.engel.wait(5)
        if self.hata:
            raise self.hata
        return {"ids": [["x"]], "documents": [["ders"]]}

    def get(self, include=None, **kwargs):
        if self.hata:
            raise self.hata
        return {"ids": list(self.eklenen), "documents": [], "metadatas": []}

    def count(self):
        return len(self.eklenen)


@pytest.fixture(autouse=True)
def _izole():
    store.reset_clients()
    yield
    store.reset_clients()


def _kilidi_tut(dizin: Path):
    tutamac = (dizin / store._LOCK_FILE).open("a")
    assert store._try_lock(tutamac)
    return tutamac


def test_yazma_basariyi_bayrakla_bildirir(tmp_path):
    korumali = store.GuardedCollection(_Koleksiyon(), tmp_path)

    assert korumali.add(ids=["a"]) is True


def test_kilit_alinamazsa_yazma_false_doner(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROCESS_LOCK_TIMEOUT_S", 0.1)
    koleksiyon = _Koleksiyon()
    korumali = store.GuardedCollection(koleksiyon, tmp_path)
    tutamac = _kilidi_tut(tmp_path)
    try:
        sonuc = korumali.add(ids=["a"])
    finally:
        tutamac.close()

    assert sonuc is False and koleksiyon.eklenen == []


def test_chroma_istisnasi_cagirana_sizmaz_okuma_bos_yazma_false(tmp_path, caplog):
    koleksiyon = _Koleksiyon()
    koleksiyon.hata = ValueError(
        "Embedding dimension 384 does not match collection dimensionality 768"
    )
    korumali = store.GuardedCollection(koleksiyon, tmp_path)

    with caplog.at_level("WARNING"):
        okuma = korumali.query(query_texts=["x"])
        yazma = korumali.add(ids=["a"])

    assert okuma["ids"] == [[]]
    assert yazma is False
    assert any("ValueError" in getattr(kayit, "hata", "") for kayit in caplog.records)


def test_bir_koleksiyonun_zaman_asimi_digerlerini_kapatmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CALL_TIMEOUT_S", 0.2)
    engel = threading.Event()
    takilan = _Koleksiyon("kod")
    takilan.engel = engel
    saglam = _Koleksiyon("dersler")
    korumali_takilan = store.GuardedCollection(takilan, tmp_path)
    korumali_saglam = store.GuardedCollection(saglam, tmp_path)
    try:
        korumali_takilan.query(query_texts=["a"])
    finally:
        # Takılan çağrı biter ve dizin kilidini bırakır; kapanış yalnız "kod"a aittir.
        engel.set()
        time.sleep(0.2)
    assert korumali_saglam.add(ids=["a"]) is True

    assert saglam.eklenen == ["a"]


def test_kapanan_koleksiyon_bekleme_suresinden_sonra_yeniden_denenir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CALL_TIMEOUT_S", 0.2)
    monkeypatch.setattr(store, "DISABLE_COOLDOWN_S", 0.3)
    engel = threading.Event()
    koleksiyon = _Koleksiyon("kod")
    koleksiyon.engel = engel
    korumali = store.GuardedCollection(koleksiyon, tmp_path)
    try:
        korumali.query(query_texts=["a"])
    finally:
        engel.set()
    assert korumali.add(ids=["a"]) is False  # kapalı: çağrı yapılmaz
    assert koleksiyon.eklenen == []
    time.sleep(0.4)
    assert korumali.add(ids=["a"]) is True  # süre doldu: tekrar açıldı


def test_yazma_gomme_suresi_icin_okuma_sinirindan_uzun_beklenir(tmp_path, monkeypatch):
    """İlk ONNX indirmesi/CPU gömme okuma sınırını aşar; yazma kapatılmamalı (M1-30)."""
    monkeypatch.setattr(store, "CALL_TIMEOUT_S", 0.1)
    monkeypatch.setattr(store, "WRITE_CALL_TIMEOUT_S", 3.0)
    koleksiyon = _Koleksiyon()
    koleksiyon.bekle = 0.4
    korumali = store.GuardedCollection(koleksiyon, tmp_path)

    assert korumali.add(ids=["a"]) is True
    assert koleksiyon.eklenen == ["a"]
    assert korumali.count() == 1  # koleksiyon kapanmadı


def test_yazilamayan_ders_eklendi_sayilmaz(tmp_path, monkeypatch):
    koleksiyon = _Koleksiyon()
    koleksiyon.hata = RuntimeError("sqlite yazılamadı")
    monkeypatch.setattr(
        lessons, "get_collection", lambda *a, **k: store.GuardedCollection(koleksiyon, tmp_path)
    )
    bellek = lessons.ChromaLessonMemory(tmp_path)

    assert bellek.add(Lesson(text="yeni ders", kind=LessonKind.SUCCESS)) is False


def test_reindex_yazilamayan_partileri_eklendi_saymaz(tmp_path, monkeypatch):
    koleksiyon = _Koleksiyon("kod")
    monkeypatch.setattr(
        code_index, "get_collection", lambda *a, **k: store.GuardedCollection(koleksiyon, tmp_path)
    )
    kok = tmp_path / "proje"
    kok.mkdir()
    (kok / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    indeks = code_index.ChromaCodeIndex(tmp_path, kok)
    koleksiyon.hata = RuntimeError("sqlite yazılamadı")

    istatistik = indeks.reindex()

    assert istatistik.total >= 1
    assert istatistik.added == 0
    assert istatistik.failed == istatistik.total
    assert istatistik.unchanged == 0


def test_reindex_ozeti_yazilamayan_parcayi_soyler():
    from fusion_cli.core.memory import IndexStats
    from fusion_cli.ui.messages import reindex_summary

    ozet = reindex_summary(IndexStats(total=5, added=2, removed=0, failed=3))

    assert "3 parça YAZILAMADI" in ozet
    assert "+2 yeni" in ozet

"""Süreçler arası bellek kilidi: paralel Fusion süreçleri ChromaDB'de kilitlenmesin."""

from __future__ import annotations

import time

from fusion_cli.memory import store


class _SahteKoleksiyon:
    def __init__(self) -> None:
        self.eklenen: list[str] = []
        self.name = "dersler"

    def add(self, ids: list[str]) -> None:
        self.eklenen.extend(ids)

    def query(self, query_texts: list[str]) -> dict[str, object]:
        return {"ids": [["d1"]], "documents": [["ders"]]}

    def count(self) -> int:
        return len(self.eklenen)


def _kilidi_tut(dizin):
    tutamac = (dizin / store._LOCK_FILE).open("a")
    assert store._try_lock(tutamac)
    return tutamac


def test_kilit_bossa_cagri_gecer(tmp_path):
    koleksiyon = _SahteKoleksiyon()
    korumali = store.GuardedCollection(koleksiyon, tmp_path)

    korumali.add(ids=["a"])

    assert koleksiyon.eklenen == ["a"]
    assert korumali.count() == 1 and korumali.name == "dersler"


def test_baska_surec_kilidi_tutarsa_cagri_atlanir_ve_bos_sonuc_doner(tmp_path, monkeypatch):
    """Ölçüldü (4 Ekim): dört paralel süreç aynı depoda bir turu sonsuza dek dondurdu."""
    monkeypatch.setattr(store, "PROCESS_LOCK_TIMEOUT_S", 0.2)
    koleksiyon = _SahteKoleksiyon()
    korumali = store.GuardedCollection(koleksiyon, tmp_path)
    tutamac = _kilidi_tut(tmp_path)
    try:
        basla = time.monotonic()
        sorgu = korumali.query(query_texts=["x"])
        korumali.add(ids=["b"])
        sayi = korumali.count()
    finally:
        tutamac.close()

    assert time.monotonic() - basla < 2
    assert sorgu["ids"] == [[]] and sayi == 0 and koleksiyon.eklenen == []


def test_takilan_cagri_sure_sinirinda_birakilir_ve_depo_kapatilir(tmp_path, monkeypatch):
    """Ölçüldü (4 Ekim): kilit altında bile çağrı ChromaDB içinde süresiz bekledi."""
    import threading

    monkeypatch.setattr(store, "CALL_TIMEOUT_S", 0.2)
    birak = threading.Event()

    class _Takilan(_SahteKoleksiyon):
        def query(self, query_texts: list[str]) -> dict[str, object]:
            birak.wait(5)
            return {"ids": [["x"]]}

    korumali = store.GuardedCollection(_Takilan(), tmp_path)
    try:
        basla = time.monotonic()
        ilk = korumali.query(query_texts=["a"])
        ikinci = korumali.count()
    finally:
        birak.set()
        store.reset_clients()

    assert time.monotonic() - basla < 2
    assert ilk["ids"] == [[]] and ikinci == 0

"""Hermes geçmiş okuyucusu."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fusion_cli.history.hermes_source import HermesSource

SEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, source TEXT, title TEXT, cwd TEXT,
    started_at REAL NOT NULL, message_count INTEGER DEFAULT 0
);
CREATE TABLE messages (
    id TEXT PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL
);
"""


def _kur(home: Path, oturumlar: list[tuple], mesajlar: list[tuple]) -> None:
    kok = home / ".hermes"
    kok.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(kok / "state.db")
    baglanti.executescript(SEMA)
    baglanti.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?)", oturumlar)
    baglanti.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", mesajlar)
    baglanti.commit()
    baglanti.close()


def test_iz_yoksa_kurulu_degil(tmp_path):
    assert HermesSource(tmp_path).is_installed() is False


def test_baslik_ve_tur_sayisi_okunur(tmp_path):
    _kur(
        tmp_path,
        [("s1", "cli", "Pazar analizi", "/x/proje", 100.0, 2)],
        [("m1", "s1", "user", "soru", 101.0), ("m2", "s1", "assistant", "cevap", 102.0)],
    )

    (ref,) = HermesSource(tmp_path).list()

    assert ref.title == "Pazar analizi"
    assert ref.turn_count == 2
    assert ref.source == "hermes"


def test_baslik_yoksa_ilk_kullanici_mesaji_kullanilir(tmp_path):
    _kur(
        tmp_path,
        [("s1", "cli", None, "/x", 100.0, 1)],
        [("m1", "s1", "user", "başlıksız oturum", 101.0)],
    )

    (ref,) = HermesSource(tmp_path).list()

    assert ref.title == "başlıksız oturum"


def test_proje_koku_verilince_o_klasor_once_gelir(tmp_path):
    _kur(
        tmp_path,
        [
            ("s1", "cli", "başka", "/baska", 100.0, 0),
            ("s2", "cli", "hedef", "/hedef", 50.0, 0),
        ],
        [],
    )

    refs = HermesSource(tmp_path).list(Path("/hedef"))

    assert refs[0].title == "hedef"


def test_proje_onceligi_diger_proje_daha_yeni_olsa_bile_korunur(tmp_path):
    # "başka" projesi daha yeni (started_at 200) ama root "/hedef" istendiği için
    # "hedef" oturumu, daha eski olmasına rağmen önde olmalı.
    _kur(
        tmp_path,
        [
            ("s1", "cli", "başka", "/baska", 200.0, 0),
            ("s2", "cli", "hedef", "/hedef", 50.0, 0),
        ],
        [],
    )

    refs = HermesSource(tmp_path).list(Path("/hedef"))

    assert [r.title for r in refs] == ["hedef", "başka"]


def test_imlec_ve_limit_uygulanir(tmp_path):
    _kur(
        tmp_path,
        [("s1", "cli", "t", "/x", 100.0, 4)],
        [(f"m{i}", "s1", "user", f"m{i}", 100.0 + i) for i in range(4)],
    )

    turlar = HermesSource(tmp_path).read("s1", cursor=1, limit=2)

    assert [t.text for t in turlar] == ["m1", "m2"]


def test_imlec_bos_mesajlar_arasinda_gecerli_turlar_uzerinden_sayilir(tmp_path):
    # m1 boş içerikli; imleç yalnızca geçerli (boş olmayan) turları saymalı.
    # Sıra: m0(geçerli), m1(boş->atlanır), m2(geçerli), m3(geçerli), m4(geçerli)
    _kur(
        tmp_path,
        [("s1", "cli", "t", "/x", 100.0, 5)],
        [
            ("m0", "s1", "user", "m0", 100.0),
            ("m1", "s1", "user", "   ", 101.0),
            ("m2", "s1", "user", "m2", 102.0),
            ("m3", "s1", "user", "m3", 103.0),
            ("m4", "s1", "user", "m4", 104.0),
        ],
    )

    turlar = HermesSource(tmp_path).read("s1", cursor=1, limit=2)

    assert [t.text for t in turlar] == ["m2", "m3"]


def test_list_limit_root_yokken_sql_seviyesinde_uygulanir(tmp_path):
    """`root` verilmediğinde öncelik sıralaması gerekmediği için `limit` SQL
    sorgusuna doğrudan uygulanabilir; sonuç yine de en yeniden eskiye sıralı
    olmalı."""
    _kur(
        tmp_path,
        [(f"s{i}", "cli", f"t{i}", "/x", 100.0 + i, 0) for i in range(5)],
        [],
    )

    refs = HermesSource(tmp_path).list(limit=2)

    assert [r.session_id for r in refs] == ["s4", "s3"]


def test_list_limit_root_ile_proje_onceligini_bozmaz(tmp_path):
    """`root` verildiğinde proje aidiyeti önceliği SQL `LIMIT`'in önüne
    geçmeli: kendi projenin eski oturumu, diğer projenin daha yeni
    oturumundan önce gelmeli — `limit` yalnızca sıralama sonrası kırpar."""
    _kur(
        tmp_path,
        [
            ("diger", "cli", "başka proje", "/baska", 200.0, 0),
            ("hedef", "cli", "hedef proje", "/hedef", 50.0, 0),
        ],
        [],
    )

    refs = HermesSource(tmp_path).list(Path("/hedef"), limit=1)

    assert [r.session_id for r in refs] == ["hedef"]


def test_list_limit_verilmezse_hepsi_doner(tmp_path):
    _kur(
        tmp_path,
        [(f"s{i}", "cli", f"t{i}", "/x", 100.0 + i, 0) for i in range(3)],
        [],
    )

    refs = HermesSource(tmp_path).list()

    assert [r.session_id for r in refs] == ["s2", "s1", "s0"]


def test_malformed_numeric_fields_do_not_crash_listing_or_reading(tmp_path) -> None:
    _kur(
        tmp_path,
        [("s1", "cli", "başlık", "/x", "bozuk-zaman", "bozuk-sayı")],
        [("m1", "s1", "user", "mesaj", "bozuk-zaman")],
    )

    (ref,) = HermesSource(tmp_path).list()
    (turn,) = HermesSource(tmp_path).read("s1")

    assert ref.updated_at == 0.0
    assert ref.turn_count == 0
    assert turn.timestamp == 0.0


def test_session_without_identifier_is_skipped(tmp_path) -> None:
    _kur(
        tmp_path,
        [
            (None, "cli", "bozuk", "/x", 200.0, 0),
            ("s1", "cli", "sağlam", "/x", 100.0, 0),
        ],
        [],
    )

    refs = HermesSource(tmp_path).list()

    assert [ref.session_id for ref in refs] == ["s1"]


def test_title_falls_back_to_date_and_size(tmp_path) -> None:
    _kur(
        tmp_path,
        [("s1", "cli", None, "/x", 1_700_000_000.0, 0)],
        [],
    )

    (ref,) = HermesSource(tmp_path).list()

    assert "2023-11-14" in ref.title
    assert "bayt" in ref.title
    assert ref.title != "s1"

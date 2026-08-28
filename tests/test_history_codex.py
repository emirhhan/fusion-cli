"""Codex/ChatGPT uygulaması geçmiş okuyucusu."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fusion_cli.history.codex_source import CodexSource

SEMA = """
CREATE TABLE thread_items (
    thread_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    rollout_ordinal INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    item_json TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT ''
);
"""


def _kur(home: Path, satirlar: list[tuple[str, int, str, dict]]) -> None:
    kok = home / ".codex"
    kok.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(kok / "thread_history_1.sqlite")
    baglanti.executescript(SEMA)
    for thread_id, ordinal, item_type, payload in satirlar:
        baglanti.execute(
            "INSERT INTO thread_items VALUES (?,?,?,?,?,?,?)",
            (thread_id, "t", f"i{ordinal}", ordinal, 0, json.dumps(payload), item_type),
        )
    baglanti.commit()
    baglanti.close()


def _indeks(home: Path, kayitlar: list[dict]) -> None:
    yol = home / ".codex" / "session_index.jsonl"
    yol.write_text("\n".join(json.dumps(k) for k in kayitlar), encoding="utf-8")


def test_iz_yoksa_kurulu_degil(tmp_path):
    assert CodexSource(tmp_path).is_installed() is False


def test_iz_varsa_kurulu(tmp_path):
    _kur(tmp_path, [])

    assert CodexSource(tmp_path).is_installed() is True


def test_indeksten_baslik_okunur(tmp_path):
    _kur(tmp_path, [])
    _indeks(
        tmp_path,
        [{"id": "th1", "thread_name": "Align Fusion CLI", "updated_at": "2026-08-27T13:13:49Z"}],
    )

    (ref,) = CodexSource(tmp_path).list()

    assert ref.title == "Align Fusion CLI"
    assert ref.source == "codex"


def test_kullanici_ve_ajan_mesajlari_okunur(tmp_path):
    _kur(
        tmp_path,
        [
            ("th1", 1, "userMessage", {"type": "userMessage", "content": [{"text": "soru"}]}),
            ("th1", 2, "agentMessage", {"type": "agentMessage", "text": "cevap"}),
        ],
    )

    turlar = CodexSource(tmp_path).read("th1")

    assert [(t.role, t.text) for t in turlar] == [("user", "soru"), ("assistant", "cevap")]


def test_imlec_ve_limit_uygulanir(tmp_path):
    _kur(
        tmp_path,
        [
            ("th1", i, "userMessage", {"type": "userMessage", "content": [{"text": f"m{i}"}]})
            for i in range(4)
        ],
    )

    turlar = CodexSource(tmp_path).read("th1", cursor=1, limit=2)

    assert [t.text for t in turlar] == ["m1", "m2"]


def test_bozuk_item_json_atlanir(tmp_path):
    _kur(
        tmp_path,
        [("th1", 1, "userMessage", {"type": "userMessage", "content": [{"text": "iyi"}]})],
    )
    baglanti = sqlite3.connect(tmp_path / ".codex" / "thread_history_1.sqlite")
    baglanti.execute("INSERT INTO thread_items VALUES ('th1','t','i9',9,0,'{bozuk','userMessage')")
    baglanti.commit()
    baglanti.close()

    turlar = CodexSource(tmp_path).read("th1")

    assert [t.text for t in turlar] == ["iyi"]


def test_bos_metin_none_dizgesi_uretmez(tmp_path):
    """SORUN 1: `{"text": null}` `str(None)` ile "None" dizgesine dönüşmemeli."""
    _kur(
        tmp_path,
        [
            ("th1", 1, "userMessage", {"type": "userMessage", "content": [{"text": None}]}),
            ("th1", 2, "userMessage", {"type": "userMessage", "content": [{"text": "gercek"}]}),
        ],
    )

    turlar = CodexSource(tmp_path).read("th1")

    assert "None" not in [t.text for t in turlar]
    assert [t.text for t in turlar] == ["gercek"]


def test_imlec_ve_limit_gecerli_turlar_uzerinden_sayilir(tmp_path):
    """SORUN 2: cursor/limit, SQL satır sırası değil GEÇERLİ (boş olmayan metinli)
    turlar üzerinden sayılmalı. Aralarda boş metinli (atlanan) satırlar vardır.

    Bu test, düzeltme geri alınıp SQL'e LIMIT/OFFSET konursa KIRMIZIYA döner:
    SQL seviyesinde LIMIT/OFFSET uygulanırsa, boş satırlar da pencereye dahil
    edilip atılacağından dönen tur sayısı ve içeriği burada beklenenden az/farklı
    olur.
    """
    satirlar = [
        ("th1", 0, "userMessage", {"type": "userMessage", "content": [{"text": "m0"}]}),
        ("th1", 1, "userMessage", {"type": "userMessage", "content": [{"text": ""}]}),
        ("th1", 2, "userMessage", {"type": "userMessage", "content": [{"text": "m1"}]}),
        ("th1", 3, "userMessage", {"type": "userMessage", "content": []}),
        ("th1", 4, "userMessage", {"type": "userMessage", "content": [{"text": "m2"}]}),
        ("th1", 5, "userMessage", {"type": "userMessage", "content": [{"text": ""}]}),
        ("th1", 6, "userMessage", {"type": "userMessage", "content": [{"text": "m3"}]}),
    ]
    _kur(tmp_path, satirlar)

    turlar = CodexSource(tmp_path).read("th1", cursor=1, limit=2)

    assert [t.text for t in turlar] == ["m1", "m2"]


def test_beklenmedik_zaman_damgasi_istisna_firlatmaz(tmp_path):
    """SORUN 3: `created_at_ms` metin gibi beklenmedik bir tip olsa bile
    `read()` istisna fırlatmadan `timestamp=0.0` ile devam etmeli."""
    kok = tmp_path / ".codex"
    kok.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(kok / "thread_history_1.sqlite")
    baglanti.executescript(SEMA)
    payload = json.dumps({"type": "userMessage", "content": [{"text": "soru"}]})
    baglanti.execute(
        "INSERT INTO thread_items VALUES (?,?,?,?,?,?,?)",
        ("th1", "t", "i1", 1, "gecersiz-zaman", payload, "userMessage"),
    )
    baglanti.commit()
    baglanti.close()

    turlar = CodexSource(tmp_path).read("th1")

    assert [t.text for t in turlar] == ["soru"]
    assert turlar[0].timestamp == 0.0


def test_list_limit_uygulanir(tmp_path):
    """`limit` verildiğinde indeksten en fazla o kadar oturum döner."""
    (tmp_path / ".codex").mkdir(parents=True, exist_ok=True)
    _indeks(
        tmp_path,
        [
            {"id": f"s{i}", "thread_name": f"t{i}", "updated_at": f"2024-01-0{i + 1}T00:00:00"}
            for i in range(5)
        ],
    )

    refs = CodexSource(tmp_path).list(limit=2)

    assert [r.session_id for r in refs] == ["s4", "s3"]


def test_list_limit_verilmezse_hepsi_doner(tmp_path):
    (tmp_path / ".codex").mkdir(parents=True, exist_ok=True)
    _indeks(
        tmp_path,
        [
            {"id": f"s{i}", "thread_name": f"t{i}", "updated_at": f"2024-01-0{i + 1}T00:00:00"}
            for i in range(3)
        ],
    )

    refs = CodexSource(tmp_path).list()

    assert [r.session_id for r in refs] == ["s2", "s1", "s0"]

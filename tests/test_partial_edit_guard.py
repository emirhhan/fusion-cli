"""Kesilmiş önizleme tam dosya yazımına dönüşemez (WP05).

`proje.oku` büyük dosyada yalnız ilk bölümü döndürür ama `sha256` dosyanın
TAMAMINA aittir. Arayüz bu kısmi içeriği düzenleyip aynı karmayla gönderirse
hash kapısı geçiyor ve dosyanın geri kalanı siliniyordu. Karma tek başına yeterli
değildir: yazma, o oturumda dosyanın tamamının okunduğunu (veya yazıldığını)
gerektirir.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fusion_cli.appserver.workspace import WorkspaceJournal, read_entry, write_entry

_ICERIK = "a" * 64 + "\nkalan önemli bölüm\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_kesilmis_okumanin_karmasiyla_yazim_reddedilir(tmp_path: Path):
    (tmp_path / "buyuk.txt").write_text(_ICERIK, encoding="utf-8")
    journal = WorkspaceJournal()
    okunan = read_entry(tmp_path, {"yol": "buyuk.txt", "max_bytes": 16}, journal)
    assert okunan["kesildi"] is True

    sonuc = write_entry(
        tmp_path,
        {"yol": "buyuk.txt", "icerik": okunan["icerik"] + "x", "expected_sha256": okunan["sha256"]},
        journal,
    )

    assert sonuc["ok"] is False
    assert sonuc["kod"] == "PARTIAL_READ"
    assert (tmp_path / "buyuk.txt").read_text(encoding="utf-8") == _ICERIK


def test_hic_okunmamis_dosyaya_dogru_karmayla_yazim_reddedilir(tmp_path: Path):
    (tmp_path / "a.txt").write_text(_ICERIK, encoding="utf-8")

    sonuc = write_entry(
        tmp_path,
        {"yol": "a.txt", "icerik": "yeni", "expected_sha256": _sha(_ICERIK)},
        WorkspaceJournal(),
    )

    assert sonuc["kod"] == "PARTIAL_READ"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == _ICERIK


def test_tam_okunan_dosya_yazilir_ve_ardisik_kayit_calisir(tmp_path: Path):
    (tmp_path / "a.txt").write_text("bir\n", encoding="utf-8")
    journal = WorkspaceJournal()
    okunan = read_entry(tmp_path, {"yol": "a.txt"}, journal)

    ilk = write_entry(
        tmp_path, {"yol": "a.txt", "icerik": "iki\n", "expected_sha256": okunan["sha256"]}, journal
    )
    ikinci = write_entry(
        tmp_path, {"yol": "a.txt", "icerik": "üç\n", "expected_sha256": ilk["sha256"]}, journal
    )

    assert ilk["ok"] is True and ikinci["ok"] is True
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "üç\n"


def test_yeni_dosya_okuma_gerektirmez(tmp_path: Path):
    sonuc = write_entry(
        tmp_path, {"yol": "yeni.txt", "icerik": "x", "expected_sha256": ""}, WorkspaceJournal()
    )

    assert sonuc["ok"] is True

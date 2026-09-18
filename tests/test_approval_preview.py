"""Onay kartı, işlem yapılmadan ÖNCE ne değişeceğini göstermeli.

Ölçüldü (17 Eylül denetimi): onay diyaloğu yalnız araç adını ve argümanlarını
gösteriyordu. Kullanıcı `write_file(path=..., content=<1500 karakter>)` görüp
dosyanın nasıl değişeceğini bilmeden onaylıyordu. Claude'da düzenleme onayı
diff ile gelir.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.appserver.approval_preview import onizleme_diffi


def test_var_olan_dosyanin_degisikligi_diff_olarak_gelir(tmp_path: Path) -> None:
    (tmp_path / "fiyat.py").write_text("KDV = 0.18\n", encoding="utf-8")

    diff = onizleme_diffi("write_file", {"path": "fiyat.py", "content": "KDV = 0.20\n"}, tmp_path)

    assert "-KDV = 0.18" in diff
    assert "+KDV = 0.20" in diff


def test_yeni_dosya_tamamen_eklenmis_gorunur(tmp_path: Path) -> None:
    diff = onizleme_diffi("write_file", {"path": "yeni.py", "content": "x = 1\n"}, tmp_path)

    assert "+x = 1" in diff
    assert "yeni.py" in diff


def test_satir_araligi_degisikligi_diff_uretir(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("bir\niki\nüç\n", encoding="utf-8")

    diff = onizleme_diffi(
        "replace_range", {"path": "a.py", "start_line": 2, "end_line": 2, "new": "İKİ"}, tmp_path
    )

    assert "-iki" in diff
    assert "+İKİ" in diff


def test_degistirmeyen_arac_icin_diff_yok(tmp_path: Path) -> None:
    assert onizleme_diffi("run_shell", {"command": "pytest"}, tmp_path) == ""


def test_okunamayan_dosya_turu_kesmez(tmp_path: Path) -> None:
    """Önizleme bir kolaylıktır: üretilemiyorsa onay akışı yine çalışmalı."""
    hedef = tmp_path / "ikili.bin"
    hedef.write_bytes(b"\x00\xff\x00")

    assert onizleme_diffi("write_file", {"path": "ikili.bin", "content": "metin"}, tmp_path) == ""

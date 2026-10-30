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


def test_tam_metin_duzenlemesi_diff_uretir(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("bir\niki\nüç\n", encoding="utf-8")

    diff = onizleme_diffi("edit_file", {"path": "a.py", "old": "iki", "new": "İKİ"}, tmp_path)

    assert "-iki" in diff
    assert "+İKİ" in diff


def test_degistirmeyen_arac_icin_diff_yok(tmp_path: Path) -> None:
    assert onizleme_diffi("run_shell", {"command": "pytest"}, tmp_path) == ""


def test_okunamayan_dosya_turu_kesmez(tmp_path: Path) -> None:
    """Önizleme bir kolaylıktır: üretilemiyorsa onay akışı yine çalışmalı."""
    hedef = tmp_path / "ikili.bin"
    hedef.write_bytes(b"\x00\xff\x00")

    assert onizleme_diffi("write_file", {"path": "ikili.bin", "content": "metin"}, tmp_path) == ""


def test_multi_edit_edits_listesi_diff_uretir(tmp_path: Path) -> None:
    """Ölçüldü (30 Ekim, S1-13): gerçek `multi_edit` şeması `edits` listesidir;
    önizleme üst düzey `old_string` aradığı için kart diffsiz çıkıyordu."""
    (tmp_path / "a.py").write_text("bir\niki\nüç\n", encoding="utf-8")
    args = {"path": "a.py", "edits": [{"old": "bir", "new": "BİR"}, {"old": "üç", "new": ""}]}

    diff = onizleme_diffi("multi_edit", args, tmp_path)

    assert "+BİR" in diff
    assert "-üç" in diff


def test_replace_all_onizlemede_tum_eslesmeleri_gosterir(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\nx\n", encoding="utf-8")

    diff = onizleme_diffi(
        "edit_file", {"path": "a.py", "old": "x", "new": "y", "replace_all": True}, tmp_path
    )

    assert diff.count("+y") == 2


def test_bos_yeni_metin_silmeyi_diff_olarak_gosterir(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("bir\niki\n", encoding="utf-8")

    diff = onizleme_diffi("edit_file", {"path": "a.py", "old": "iki\n", "new": ""}, tmp_path)

    assert "-iki" in diff


def test_kok_disindaki_dosya_onizlenmez(tmp_path: Path) -> None:
    """Kısıtlı kipte araç kök dışına yazmayı reddeder; önizleme de içeriği okumaz."""
    kok = tmp_path / "kok"
    kok.mkdir()
    dis = tmp_path / "gizli.txt"
    dis.write_text("sır\n", encoding="utf-8")

    assert onizleme_diffi("write_file", {"path": str(dis), "content": "x\n"}, kok) == ""
    assert onizleme_diffi("write_file", {"path": "../gizli.txt", "content": "x\n"}, kok) == ""


def test_cok_buyuk_dosya_onizlenmez(tmp_path: Path) -> None:
    (tmp_path / "buyuk.txt").write_text("a" * (2 * 1024 * 1024), encoding="utf-8")

    assert onizleme_diffi("write_file", {"path": "buyuk.txt", "content": "b"}, tmp_path) == ""


# --- Dalga 4 (T1-65) -----------------------------------------------------------------------


def test_cok_buyuk_dosyada_difflib_yerine_ozet_verilir():
    """`difflib.unified_diff` onbinlerce satırda ikinci derece yavaşlıyordu."""
    from fusion_cli.tools import diffing

    eski = "\n".join(f"satir {i}" for i in range(diffing.MAX_DIFF_LINES + 100))
    yeni = eski.replace("satir 500\n", "DEGISTI\n", 1)

    sonuc = diffing.bounded_diff(eski, yeni, "b.js")

    assert "ayrıntılı fark gösterilmedi" in sonuc
    assert "501" in sonuc  # ilk değişen satır (1 tabanlı)
    assert len(sonuc.splitlines()) < 5


def test_kucuk_dosyada_normal_diff_surer():
    from fusion_cli.tools import diffing

    sonuc = diffing.bounded_diff("a\nb\n", "a\nc\n", "x.txt")

    assert "-b" in sonuc and "+c" in sonuc


# --- Dalga 4 (T2-38) -----------------------------------------------------------------------


def test_onizleme_replace_all_metin_true_ile_gercek_aracla_ayni(tmp_path):
    """edit_file `replace_all: "true"` kabul eder; önizleme de aynısını göstermeli."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.preview import _preview_edit

    (tmp_path / "a.txt").write_text("x x x\n", encoding="utf-8")
    onizleme = _preview_edit(
        {"path": "a.txt", "old": "x", "new": "y", "replace_all": "true"},
        ToolContext(root=tmp_path),
    )

    assert onizleme.count("+y y y") == 1

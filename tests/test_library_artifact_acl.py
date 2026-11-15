"""Kitaplıkta kayıt kaldırma yetkisi ve bağlı dosya davranışı.

Ölçüldü (29 Ekim): `kitaplik.kaldir` yalnız dizine "kaldırıldı" satırı ekler;
hiçbir koşulda dosya silmez. Dizinde kayıtlı olmayan yol (galeri görseli, `..`
ile kaçan yol, başka kök, symlink) reddedilir ve diske/dizine dokunulmaz.
Dizin satırı elle bozulsa bile liste kayıt kapsamı dışındaki dosyayı göstermez.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver import library


def _dirs(tmp_path):
    return tmp_path / "kitaplik", tmp_path / "galeri"


def _proje(tmp_path, ad="proje"):
    root = tmp_path / ad
    root.mkdir()
    return root


def _satirlar(base):
    return library._index_path(base).read_text(encoding="utf-8").splitlines()


def test_kaldirma_hicbir_kaynakta_dosya_silmez(tmp_path):
    base, gallery = _dirs(tmp_path)
    root = _proje(tmp_path)
    (root / "a.txt").write_text("a", encoding="utf-8")
    library.record_generated(root, ["a.txt"], base)
    disarida = tmp_path / "belge.md"
    disarida.write_text("b", encoding="utf-8")
    yuklenen = library.add_upload({"yol": str(disarida)}, base)["yol"]
    for item in library.list_library({}, base, gallery)["dosyalar"]:
        assert library.remove_entry({"yol": item["yol"]}, base) == {"ok": True}
    assert (root / "a.txt").is_file() and disarida.is_file()
    # Yüklenen kopya da yerinde kalır: kayıt kalkar, dosya ayrı karardır.
    assert Path(yuklenen).is_file()
    assert library.list_library({}, base, gallery)["dosyalar"] == []


@pytest.mark.parametrize("tur", ["galeri", "nokta_nokta", "goreli", "baska_kok_dosyasi", "dizin"])
def test_kayitsiz_yol_reddedilir_dosya_ve_dizin_degismez(tmp_path, tur):
    base, gallery = _dirs(tmp_path)
    gallery.mkdir()
    root = _proje(tmp_path)
    baska = _proje(tmp_path, "baska")
    (root / "a.txt").write_text("a", encoding="utf-8")
    (baska / "gizli.txt").write_text("g", encoding="utf-8")
    (gallery / "g.png").write_bytes(b"png")
    library.record_generated(root, ["a.txt"], base)
    oncesi = _satirlar(base)
    yol = {
        "galeri": str(gallery / "g.png"),
        "nokta_nokta": str(root / ".." / "baska" / "gizli.txt"),
        "goreli": "a.txt",
        "baska_kok_dosyasi": str(baska / "gizli.txt"),
        "dizin": str(root),
    }[tur]

    sonuc = library.remove_entry({"yol": yol}, base)

    assert sonuc["ok"] is False
    assert _satirlar(base) == oncesi
    assert (gallery / "g.png").is_file() and (baska / "gizli.txt").is_file()


@pytest.mark.parametrize("deger", [None, 5, ["x"], {"a": 1}, ""])
def test_gecersiz_yol_turu_reddedilir(tmp_path, deger):
    base, _ = _dirs(tmp_path)
    assert library.remove_entry({"yol": deger}, base)["ok"] is False
    assert library.remove_entry({}, base)["ok"] is False


def test_kokun_disina_kacan_symlink_kayda_girmez_ve_listelenmez(tmp_path):
    base, gallery = _dirs(tmp_path)
    root = _proje(tmp_path)
    disari = tmp_path / "gizli.txt"
    disari.write_text("g", encoding="utf-8")
    (root / "kisa.txt").symlink_to(disari)

    assert library.record_generated(root, ["kisa.txt"], base) == 0
    assert library.list_library({}, base, gallery)["dosyalar"] == []


def test_elle_bozulan_dizin_kapsam_disi_dosyayi_gostermez(tmp_path):
    base, gallery = _dirs(tmp_path)
    root = _proje(tmp_path)
    disari = tmp_path / "gizli.txt"
    disari.write_text("g", encoding="utf-8")
    base.mkdir()
    zararli = [
        {"yol": str(disari), "kaynak": "uretilen", "kok": str(root), "zaman": 1},
        {"yol": str(disari), "kaynak": "yuklenen", "zaman": 1},
        {"yol": str(root / ".." / "gizli.txt"), "kaynak": "uretilen", "kok": str(root)},
        {"yol": str(disari), "kaynak": "gorsel", "kok": str(root)},
    ]
    library._index_path(base).write_text(
        "\n".join(json.dumps(item) for item in zararli) + "\n", encoding="utf-8"
    )
    assert library.list_library({}, base, gallery)["dosyalar"] == []


def test_kayittan_sonra_symlinke_cevrilen_dosya_listeden_duser(tmp_path):
    base, gallery = _dirs(tmp_path)
    root = _proje(tmp_path)
    hedef = root / "a.txt"
    hedef.write_text("a", encoding="utf-8")
    library.record_generated(root, ["a.txt"], base)
    disari = tmp_path / "gizli.txt"
    disari.write_text("g", encoding="utf-8")
    hedef.unlink()
    hedef.symlink_to(disari)
    assert library.list_library({}, base, gallery)["dosyalar"] == []


def test_ayni_adli_dosya_baska_kokte_kaldirmadan_etkilenmez(tmp_path):
    base, gallery = _dirs(tmp_path)
    a, b = _proje(tmp_path, "a"), _proje(tmp_path, "b")
    (a / "rapor.md").write_text("a", encoding="utf-8")
    (b / "rapor.md").write_text("b", encoding="utf-8")
    library.record_generated(a, ["rapor.md"], base)
    library.record_generated(b, ["rapor.md"], base)
    assert library.remove_entry({"yol": str(a / "rapor.md")}, base) == {"ok": True}
    kalan = library.list_library({}, base, gallery)["dosyalar"]
    assert [item["yol"] for item in kalan] == [str((b / "rapor.md").resolve())]


def test_kaldirilan_kayit_ancak_yeni_gercek_degisiklikle_geri_gelir(tmp_path):
    base, gallery = _dirs(tmp_path)
    root = _proje(tmp_path)
    (root / "a.txt").write_text("a", encoding="utf-8")
    library.record_generated(root, ["a.txt"], base)
    yol = library.list_library({}, base, gallery)["dosyalar"][0]["yol"]
    library.remove_entry({"yol": yol}, base)
    assert library.list_library({}, base, gallery)["dosyalar"] == []
    # Aynı yolun turda yeniden değişmesi (FilesChanged) yeni bir kayıttır.
    assert library.record_generated(root, ["a.txt"], base) == 1
    assert len(library.list_library({}, base, gallery)["dosyalar"]) == 1

"""Kitaplık: üretilen, yüklenen ve galeri dosyalarının tek listesi."""

from __future__ import annotations

import os

from fusion_cli.appserver import library


def _dirs(tmp_path):
    return tmp_path / "kitaplik", tmp_path / "galeri"


def test_turda_degisen_dosyalar_kitapliga_girer(tmp_path):
    base, gallery = _dirs(tmp_path)
    root = tmp_path / "proje"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "rapor.md").write_text("# Rapor\n", encoding="utf-8")

    recorded = library.record_generated(
        root, ["src/app.py", str(root / "rapor.md"), "yok.txt"], base
    )
    result = library.list_library({}, base, gallery)

    assert recorded == 2
    assert {item["ad"] for item in result["dosyalar"]} == {"app.py", "rapor.md"}
    assert {item["kaynak"] for item in result["dosyalar"]} == {library.SOURCE_GENERATED}
    assert all(item["kok"] == str(root) for item in result["dosyalar"])


def test_ayni_dosya_iki_kez_listelenmez_ve_silinen_dosya_gorunmez(tmp_path):
    base, gallery = _dirs(tmp_path)
    root = tmp_path / "proje"
    root.mkdir()
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")
    library.record_generated(root, ["a.txt", "b.txt"], base)
    library.record_generated(root, ["a.txt"], base)
    (root / "b.txt").unlink()

    result = library.list_library({}, base, gallery)

    assert [item["ad"] for item in result["dosyalar"]] == ["a.txt"]
    assert result["toplam"] == 1


def test_yuklenen_dosya_kopyalanir_ve_ad_cakismasi_cozulur(tmp_path):
    base, gallery = _dirs(tmp_path)
    source = tmp_path / "fatura.pdf"
    source.write_bytes(b"%PDF")

    first = library.add_upload({"yol": str(source)}, base)
    second = library.add_upload({"yol": str(source)}, base)
    result = library.list_library({"tur": "belge"}, base, gallery)

    assert first["ok"] and second["ok"] and first["yol"] != second["yol"]
    assert sorted(item["ad"] for item in result["dosyalar"]) == ["fatura-2.pdf", "fatura.pdf"]
    assert {item["kaynak"] for item in result["dosyalar"]} == {library.SOURCE_UPLOADED}
    assert source.is_file()


def test_gecersiz_yukleme_reddedilir(tmp_path, monkeypatch):
    base, _ = _dirs(tmp_path)
    big = tmp_path / "buyuk.bin"
    big.write_bytes(b"12345")
    monkeypatch.setattr(library, "MAX_UPLOAD_BYTES", 4)

    assert library.add_upload({}, base)["ok"] is False
    assert library.add_upload({"yol": str(tmp_path / "yok.txt")}, base)["ok"] is False
    assert "sınır" in library.add_upload({"yol": str(big)}, base)["metin"]
    assert not (base / "yuklenenler" / "buyuk.bin").exists()


def test_galeri_gorselleri_listeye_katilir_tur_ve_sorgu_suzer(tmp_path):
    base, gallery = _dirs(tmp_path)
    gallery.mkdir()
    (gallery / "kask.png").write_bytes(b"png")
    (gallery / "kask.png.json").write_text("{}", encoding="utf-8")
    root = tmp_path / "proje"
    root.mkdir()
    (root / "kask_notu.md").write_text("not", encoding="utf-8")
    (root / "main.py").write_text("pass", encoding="utf-8")
    library.record_generated(root, ["kask_notu.md", "main.py"], base)

    images = library.list_library({"tur": "gorsel"}, base, gallery)["dosyalar"]
    matches = library.list_library({"sorgu": "KASK"}, base, gallery)["dosyalar"]

    assert [(item["ad"], item["kaynak"]) for item in images] == [("kask.png", library.SOURCE_IMAGE)]
    assert sorted(item["ad"] for item in matches) == ["kask.png", "kask_notu.md"]


def test_kaldirilan_kayit_listeden_duser_dosya_yerinde_kalir(tmp_path):
    base, gallery = _dirs(tmp_path)
    root = tmp_path / "proje"
    root.mkdir()
    target = root / "a.txt"
    target.write_text("a", encoding="utf-8")
    library.record_generated(root, ["a.txt"], base)
    path = library.list_library({}, base, gallery)["dosyalar"][0]["yol"]

    assert library.remove_entry({"yol": path}, base) == {"ok": True}
    assert library.list_library({}, base, gallery)["dosyalar"] == []
    assert target.is_file()
    assert library.remove_entry({"yol": path}, base)["ok"] is False


def test_liste_yeniden_eskiye_siralanir_ve_bozuk_satir_atlanir(tmp_path):
    base, gallery = _dirs(tmp_path)
    root = tmp_path / "proje"
    root.mkdir()
    for index, name in enumerate(["eski.txt", "yeni.txt"]):
        path = root / name
        path.write_text(name, encoding="utf-8")
        os.utime(path, (1_000 + index, 1_000 + index))
    library.record_generated(root, ["eski.txt", "yeni.txt"], base)
    with (base / "kayitlar.jsonl").open("a", encoding="utf-8") as index_file:
        index_file.write("bozuk\n[1]\n")

    names = [item["ad"] for item in library.list_library({}, base, gallery)["dosyalar"]]

    assert names == ["yeni.txt", "eski.txt"]


def test_tur_siniflandirmasi():
    from pathlib import Path

    assert library.kind_of(Path("a.PNG")) == "gorsel"
    assert library.kind_of(Path("a.mp4")) == "video"
    assert library.kind_of(Path("a.tsx")) == "kod"
    assert library.kind_of(Path("a.bin")) == library.KIND_OTHER


def test_sink_degisen_dosyalari_yazar_ve_olayi_iletir(tmp_path):
    from fusion_cli.core.events import FilesChanged, StatusChanged

    base, gallery = _dirs(tmp_path)
    root = tmp_path / "proje"
    root.mkdir()
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    seen = []

    class _Inner:
        def handle(self, event):
            seen.append(event)

    sink = library.LibrarySink(_Inner(), root, base)
    events = [StatusChanged(message="çalışıyor"), FilesChanged(paths=("index.html",))]
    for event in events:
        sink.handle(event)

    assert seen == events
    assert [item["ad"] for item in library.list_library({}, base, gallery)["dosyalar"]] == [
        "index.html"
    ]

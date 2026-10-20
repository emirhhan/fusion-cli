"""`proje.dosya_ara`: `@` ile dosya anmanın sunucu tarafı."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.appserver.file_search import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    FileSearchIndex,
    search_project_files,
)


class _SahteSaat:
    """Testin ilerletebildiği monoton saat."""

    def __init__(self) -> None:
        self.deger = 0.0

    def monotonic(self) -> float:
        return self.deger

    def now(self) -> float:
        return self.deger


def _proje(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "composer.py").write_text("x = 1\n", "utf-8")
    (tmp_path / "src" / "repo_map.py").write_text("y = 2\n", "utf-8")
    (tmp_path / "README.md").write_text("# proje\n", "utf-8")
    return tmp_path


def test_sorgu_eslesen_dosyalari_doner(tmp_path):
    sonuc = search_project_files(FileSearchIndex(), _proje(tmp_path), {"sorgu": "composer"})

    assert sonuc["ok"] is True
    assert [item["yol"] for item in sonuc["sonuclar"]] == ["src/composer.py"]


def test_bos_sorgu_hata_degildir(tmp_path):
    """`@` yazılır yazılmaz liste açılır; kullanıcı henüz bir şey yazmadı."""
    sonuc = search_project_files(FileSearchIndex(), _proje(tmp_path), {"sorgu": ""})

    assert sonuc["ok"] is True
    assert len(sonuc["sonuclar"]) == 3


def test_vurgu_konumlari_tasinir(tmp_path):
    """Arayüz eşleşen harfleri kalınlaştırıyor; konumlar RPC'den gelmeli."""
    sonuc = search_project_files(FileSearchIndex(), _proje(tmp_path), {"sorgu": "repo"})

    (ilk,) = sonuc["sonuclar"]
    assert ilk["vurgu"] == [4, 5, 6, 7]


def test_gecersiz_limit_varsayilana_duser(tmp_path):
    sonuc = search_project_files(FileSearchIndex(), _proje(tmp_path), {"limit": "cok"})

    assert sonuc["ok"] is True
    assert len(sonuc["sonuclar"]) <= DEFAULT_LIMIT


def test_limit_tavani_asilmaz(tmp_path):
    sonuc = search_project_files(FileSearchIndex(), _proje(tmp_path), {"limit": 10_000})

    assert len(sonuc["sonuclar"]) <= MAX_LIMIT


def test_onbellek_ttl_icinde_diske_gitmez(tmp_path):
    """Her tuş vuruşunda disk taranmaz."""
    saat = _SahteSaat()
    index = FileSearchIndex(clock=saat, ttl_s=2.0)
    root = _proje(tmp_path)
    search_project_files(index, root, {"sorgu": ""})

    (root / "sonradan.py").write_text("z = 3\n", "utf-8")
    sonuc = search_project_files(index, root, {"sorgu": "sonradan"})

    assert sonuc["sonuclar"] == []


def test_ttl_dolunca_yeni_dosya_gorunur(tmp_path):
    """Agent'ın az önce yazdığı dosya listede görünmeli."""
    saat = _SahteSaat()
    index = FileSearchIndex(clock=saat, ttl_s=2.0)
    root = _proje(tmp_path)
    search_project_files(index, root, {"sorgu": ""})

    (root / "sonradan.py").write_text("z = 3\n", "utf-8")
    saat.deger += 3.0
    sonuc = search_project_files(index, root, {"sorgu": "sonradan"})

    assert [item["yol"] for item in sonuc["sonuclar"]] == ["sonradan.py"]


def test_invalidate_onbellegi_dusurur(tmp_path):
    """Kök değişince eski projenin dosyaları önerilmemeli."""
    saat = _SahteSaat()
    index = FileSearchIndex(clock=saat, ttl_s=60.0)
    root = _proje(tmp_path)
    search_project_files(index, root, {"sorgu": ""})

    (root / "sonradan.py").write_text("z = 3\n", "utf-8")
    index.invalidate()
    sonuc = search_project_files(index, root, {"sorgu": "sonradan"})

    assert [item["yol"] for item in sonuc["sonuclar"]] == ["sonradan.py"]

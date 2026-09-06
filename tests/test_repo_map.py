"""Depo haritası: bütçeye sığan, ÖNEMLİ sembollerden oluşan yerelleştirme özeti.

Aider'ın ölçümü: sembol grafiğini çıkarıp referans sayısına göre sıralamak, büyük
depoda hem ucuz kalmanın hem doğru dosyayı bulmanın ana yolu. Fusion'da yalnız grep
vardı: model doğru dosyayı bulmak için tur harcıyordu.

Harita TAHMİN ETMEZ: yalnız kaynakta gerçekten yazan tanımları ve referansları
sayar. Bütçe dolduğunda en çok referans alan semboller kalır.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.repo_map import build_repo_map


def _proje(tmp_path: Path) -> Path:
    (tmp_path / "sabitler.py").write_text(
        "VERGI = 0.2\n\n\ndef oran():\n    return VERGI\n", "utf-8"
    )
    (tmp_path / "fatura.py").write_text(
        "from sabitler import oran\n\n\ndef toplam(t):\n    return t * oran()\n", "utf-8"
    )
    (tmp_path / "rapor.py").write_text(
        "from fatura import toplam\n\n\ndef ozet(x):\n    return toplam(x)\n", "utf-8"
    )
    return tmp_path


def test_harita_tanimlari_dosyasiyla_listeler(tmp_path):
    harita = build_repo_map(_proje(tmp_path), budget_chars=2_000)

    assert "sabitler.py" in harita
    assert "def oran" in harita or "oran" in harita


def test_cok_referans_alan_sembol_one_gecer(tmp_path):
    harita = build_repo_map(_proje(tmp_path), budget_chars=120)

    # `toplam` iki dosyada geçiyor (tanım + kullanım); dar bütçede o kalmalı.
    assert "toplam" in harita


def test_butce_asilmaz(tmp_path):
    harita = build_repo_map(_proje(tmp_path), budget_chars=100)

    assert len(harita) <= 100


def test_bos_projede_bos_harita(tmp_path):
    assert build_repo_map(tmp_path, budget_chars=500) == ""


def test_gurultu_dizinleri_atlanir(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "paket.py").write_text("def gurultu():\n    pass\n", "utf-8")
    (tmp_path / "kod.py").write_text("def gercek():\n    pass\n", "utf-8")

    harita = build_repo_map(tmp_path, budget_chars=1_000)

    assert "gercek" in harita
    assert "gurultu" not in harita

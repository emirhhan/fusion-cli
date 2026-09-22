"""Depo haritası: bütçeye sığan, ÖNEMLİ sembollerden oluşan yerelleştirme özeti.

Aider'ın ölçümü: sembol grafiğini çıkarıp referans sayısına göre sıralamak, büyük
depoda hem ucuz kalmanın hem doğru dosyayı bulmanın ana yolu. Fusion'da yalnız grep
vardı: model doğru dosyayı bulmak için tur harcıyordu.

Harita TAHMİN ETMEZ: yalnız kaynakta gerçekten yazan tanımları ve referansları
sayar. Bütçe dolduğunda en çok referans alan semboller kalır.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fusion_cli.core import repo_map
from fusion_cli.core.repo_map import _MAX_PER_SYMBOL, build_repo_map


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


def test_git_bilinen_dosyalarla_calisir(tmp_path):
    """Depo git ise dosya listesi git'ten gelir."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "kod.py").write_text("def gercek():\n    pass\n", "utf-8")

    harita = build_repo_map(tmp_path, budget_chars=1_000)

    assert "gercek" in harita


def test_gitignore_edilen_dosya_haritaya_girmez(tmp_path):
    """`.gitignore`'daki üretilmiş ağaç haritayı yemez.

    Gerçek bulgu (22 Eylül): bu deponun haritasının ilk altı sırası
    `app/src-tauri/resources/runtime/unpacked/` altındaki paketli runtime
    kopyasından geliyordu — litellm ve httpx sembolleri, projenin kendi kodu
    listeye hiç giremiyordu.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("uretilmis/\n", "utf-8")
    uretilmis = tmp_path / "uretilmis"
    uretilmis.mkdir()
    (uretilmis / "paket.py").write_text("def gurultu():\n    pass\n", "utf-8")
    (tmp_path / "kod.py").write_text("def gercek():\n    pass\n", "utf-8")

    harita = build_repo_map(tmp_path, budget_chars=1_000)

    assert "gercek" in harita
    assert "gurultu" not in harita


def test_yeni_yazilan_izlenmeyen_dosya_haritaya_girer(tmp_path):
    """Agent'ın az önce oluşturduğu dosya haritada görünür.

    `git ls-files --cached` tek başına yetmez: henüz `git add` edilmemiş dosya
    listeye girmezse harita turun gerisinde kalır.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "yeni.py").write_text("def taze():\n    pass\n", "utf-8")

    assert "taze" in build_repo_map(tmp_path, budget_chars=1_000)


def test_onbellek_dosya_degisince_yenilenir(tmp_path):
    """Kaynak değişince harita da değişir — önbellek eski cevabı vermez."""
    hedef = tmp_path / "kod.py"
    hedef.write_text("def birinci():\n    pass\n", "utf-8")
    ilk = build_repo_map(tmp_path, budget_chars=1_000)
    assert "birinci" in ilk

    hedef.write_text("def ikinci_uzun_ad():\n    pass\n", "utf-8")
    sonra = build_repo_map(tmp_path, budget_chars=1_000)

    assert "ikinci_uzun_ad" in sonra
    assert "birinci" not in sonra


def test_ayni_ad_haritayi_ele_gecirmez(tmp_path):
    """Aynı isimli tanım en çok `_MAX_PER_SYMBOL` kez listelenir.

    Ölçülen hata: en sık kullanılan isim bütün bütçeyi yiyordu — bu deponun
    haritasının ilk dokuz satırı dokuz ayrı dosyadaki `config` fixture'ıydı.
    """
    for sira in range(6):
        (tmp_path / f"dosya{sira}.py").write_text("def config():\n    pass\n", "utf-8")
    (tmp_path / "baska.py").write_text("def tekil():\n    pass\n", "utf-8")

    harita = build_repo_map(tmp_path, budget_chars=2_000)

    assert harita.count(": config") <= _MAX_PER_SYMBOL
    assert "tekil" in harita


def test_dosya_tavani_asilinca_kismi_oldugunu_soyler(tmp_path, monkeypatch):
    """Tavan aşılırsa harita üretilir ama kısmi olduğunu SÖYLER."""
    monkeypatch.setattr(repo_map, "_MAX_FILES", 2)
    for sira in range(5):
        (tmp_path / f"dosya{sira}.py").write_text(f"def islev{sira}():\n    pass\n", "utf-8")

    harita = build_repo_map(tmp_path, budget_chars=2_000)

    assert "kısmi" in harita

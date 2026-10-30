"""Kullanıcı klasörü araması ve beceri sayfaları (T2-26, T2-27)."""

from __future__ import annotations

from fusion_cli.tools import skill_pages, user_folders


def test_arama_butcesi_klasorler_arasinda_paylasilmaz(tmp_path, monkeypatch):
    """T2-26: Documents 4000 dizini tüketince Desktop hiç taranmıyordu."""
    monkeypatch.setattr(user_folders, "MAX_VISITED_DIRS", 5)
    for i in range(20):
        (tmp_path / "Documents" / f"d{i}").mkdir(parents=True)
    (tmp_path / "Desktop" / "proje").mkdir(parents=True)
    (tmp_path / "Desktop" / "proje" / "rapor.txt").write_text("x", encoding="utf-8")

    bulunan = user_folders.find_in_user_folders("rapor.txt", home=tmp_path)

    assert [p.name for p in bulunan] == ["rapor.txt"]


def test_masaustu_ilk_sirada_aranir(tmp_path):
    for klasor in ("Documents", "Desktop"):
        (tmp_path / klasor).mkdir()
        (tmp_path / klasor / "a.txt").write_text(klasor, encoding="utf-8")

    bulunan = user_folders.find_in_user_folders("a.txt", home=tmp_path)

    assert bulunan[0].parent.name == "Desktop"


def test_cok_dosyali_skillde_kirpilan_dosya_sayisi_bildirilir(tmp_path):
    """T2-27: 40'tan fazla ek dosya sessizce listeden düşüyordu."""
    skill = tmp_path / "SKILL.md"
    skill.write_text("# s", encoding="utf-8")
    for i in range(skill_pages._MAX_SKILL_FILES + 7):
        (tmp_path / f"f{i:03d}.md").write_text("x", encoding="utf-8")

    dosyalar = skill_pages.skill_files(skill)

    assert len(dosyalar) == skill_pages._MAX_SKILL_FILES + 1
    assert "+7 dosya daha" in dosyalar[-1]


def test_kirpilan_dosya_adiyla_yine_okunabilir(tmp_path):
    skill = tmp_path / "SKILL.md"
    skill.write_text("# s", encoding="utf-8")
    for i in range(skill_pages._MAX_SKILL_FILES + 3):
        (tmp_path / f"f{i:03d}.md").write_text("x", encoding="utf-8")

    assert skill_pages.skill_file(skill, f"f{skill_pages._MAX_SKILL_FILES + 2:03d}.md") is not None


def test_load_skill_text_kirpmayi_bildirir(tmp_path):
    """T2-27: eski fonksiyon hâlâ KIRPMA BİLDİRMEDEN kesiyordu."""
    yol = tmp_path / "SKILL.md"
    yol.write_text("a" * 100, encoding="utf-8")

    metin = skill_pages.load_skill_text(yol, budget=40)

    assert metin.startswith("a" * 40)
    assert "KIRPILDI" in metin and "60 karakter" in metin
    assert skill_pages.load_skill_text(yol, budget=500) == "a" * 100

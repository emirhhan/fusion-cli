"""Proje kökünde olmayan dosyayı kullanıcı klasörlerinde bulma."""

from __future__ import annotations

from fusion_cli.tools.user_folders import find_in_user_folders, user_folder_hint


def test_belgeler_altindaki_dosyayi_adina_gore_bulur(tmp_path):
    hedef = tmp_path / "Documents" / "is" / "notlar.txt"
    hedef.parent.mkdir(parents=True)
    hedef.write_text("x", encoding="utf-8")

    assert find_in_user_folders("notlar.txt", home=tmp_path) == (hedef,)


def test_gizli_ve_bagimlilik_klasorlerini_atlar(tmp_path):
    for ad in (".git", "node_modules", ".venv"):
        gizli = tmp_path / "Desktop" / ad / "notlar.txt"
        gizli.parent.mkdir(parents=True)
        gizli.write_text("x", encoding="utf-8")

    assert find_in_user_folders("notlar.txt", home=tmp_path) == ()


def test_sonuc_sayisi_sinirlidir(tmp_path):
    for i in range(20):
        yol = tmp_path / "Downloads" / f"k{i}" / "a.txt"
        yol.parent.mkdir(parents=True)
        yol.write_text("x", encoding="utf-8")

    assert len(find_in_user_folders("a.txt", home=tmp_path)) == 5


def test_ipucu_birden_cok_eslesmede_kullaniciya_sormayi_soyler(tmp_path):
    for k in ("a", "b"):
        yol = tmp_path / "Documents" / k / "x.md"
        yol.parent.mkdir(parents=True)
        yol.write_text("x", encoding="utf-8")

    ipucu = user_folder_hint("x.md", home=tmp_path)

    assert str(tmp_path / "Documents" / "a" / "x.md") in ipucu
    assert "ask_user" in ipucu


def test_eslesme_yoksa_gizli_klasorler_icin_kullaniciya_sormayi_soyler(tmp_path):
    ipucu = user_folder_hint("yok.md", home=tmp_path)

    assert "ask_user" in ipucu
    assert "node_modules" in ipucu
    assert "ÖNCE" in ipucu


def test_ask_user_her_onay_kipinde_daima_sunulur():
    from fusion_cli.engines.agent.loop import ALWAYS_ALLOWED

    assert "ask_user" in ALWAYS_ALLOWED

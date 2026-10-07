"""Dar uzmanlık notu: yalnız kesin görev türünde tek, kısa beceri metni."""

from __future__ import annotations

from fusion_cli.config.paths import bundled_skills_dir
from fusion_cli.engines.agent.expertise import MAX_EXPERTISE_CHARS, expertise_hint


def test_oyun_varlik_hud_ve_dogrulama_talimatlari_kirpilmadan_verilir():
    hint = expertise_hint("HTML canvas oyun yap")
    assert hint is not None
    assert "açık eşleme" in hint and "HUD'ın" in hint
    assert "VARLIK KANITI" in hint and "Masaüstüne" in hint


def _not(gorev: str) -> str | None:
    return expertise_hint(gorev, bundled_skills_dir())


def test_animasyonlu_sayfa_hareket_becerisini_alir():
    metin = _not("Bir kahve markası için animasyonlu tek sayfalık tanıtım sitesi yap")
    assert metin is not None and "hareket" in metin and "prefers-reduced-motion" in metin


def test_html_oyun_ve_remotion_kendi_becerisini_alir():
    oyun = _not("index.html ile tarayıcıda oynanan 2D bir oyun yap")
    video = _not("Remotion ile 10 saniyelik animasyonlu ürün videosu üret")
    assert oyun is not None and "__GAME_STATE__" in oyun
    assert video is not None and "useCurrentFrame" in video


def test_belirsiz_ya_da_baska_alan_gorevi_not_almaz():
    assert _not("Bu fonksiyondaki hatayı düzelt") is None
    assert _not("Godot ile animasyonlu bir platform oyunu yap") is None


def test_not_kisa_tutulur_ve_on_madde_tasimaz():
    metin = _not("animasyonlu landing page") or ""
    assert len(metin) <= MAX_EXPERTISE_CHARS + 200 and "description:" not in metin


def test_beceri_dosyasi_yoksa_not_yok(tmp_path):
    assert expertise_hint("animasyonlu sayfa", tmp_path) is None


def test_remotion_becerisi_hareket_kitinin_gercek_yolunu_verir():
    """Kullanıcı (6 Ekim 2026): video "fade + yazı" kadar basitti; kit gerçek yolla verilir."""
    from fusion_cli.config.paths import bundled_skills_dir

    not_ = expertise_hint("Remotion ile tanıtım videosu yap")

    kit = bundled_skills_dir() / "remotion-video" / "kit"
    assert not_ is not None and str(kit) in not_ and "{SKILL_DIR}" not in not_
    assert (kit / "index.ts").is_file() and (kit / "KineticText.tsx").is_file()

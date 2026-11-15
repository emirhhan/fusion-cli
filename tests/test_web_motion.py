"""Layout özelliği canlandırma bulgusu: hareket transform/opacity ile yapılmalı."""

from __future__ import annotations

from fusion_cli.engines.agent.web_motion import layout_animations, size_animations
from fusion_cli.engines.agent.web_verify import inspect_web_output_by_severity


def test_width_ve_left_gecisi_ve_layout_keyframe_bulunur():
    css = (
        ".a::after{transition: top .3s ease, opacity .2s}"
        ".m{transition-property: left}"
        "@keyframes kay{from{margin-left:0}to{margin-left:20px}}"
    )

    bulgu = layout_animations(css)

    assert len(bulgu) == 1
    assert "transition: top" in bulgu[0] and "transition: left" in bulgu[0]
    assert "@keyframes kay: margin-left" in bulgu[0] and "scaleX" in bulgu[0]


def test_transform_ve_opacity_temiz_sayilir():
    css = ".a{transition: transform .3s, opacity .2s}@keyframes f{to{transform:none;opacity:1}}"
    assert layout_animations(css) == []


def test_bulgu_web_kapisinda_bloklayan_siniftadir():
    dosyalar = {
        "index.html": "<!doctype html><html><head><title>x</title></head><body><main>x</main>"
        "</body></html>",
        "style.css": ".a{transition: top .3s}",
    }
    blocking, _uyari, _oneri = inspect_web_output_by_severity(dosyalar)
    assert any("Layout özelliği" in b for b in blocking)


def test_akordeon_ve_ilerleme_cubugu_gecisi_engel_degil_uyaridir():
    """Ölçüldü (30 Ekim, A4-43): `max-height`/`width` geçişi yaygın ve çoğu kez bilinçli;
    eskiden BLOCKING olup düzeltici tur bütçesini yiyordu."""
    css = ".acc{transition: max-height .3s ease}.bar{transition: width .4s}"
    assert layout_animations(css) == []
    uyari = size_animations(css)
    assert len(uyari) == 1 and "max-height" in uyari[0] and "width" in uyari[0]

    dosyalar = {
        "index.html": "<!doctype html><html><head><title>x</title></head><body><main>x</main>"
        "</body></html>",
        "style.css": css,
    }
    blocking, uyarilar, _oneri = inspect_web_output_by_severity(dosyalar)
    assert not any("canlandırılıyor" in b for b in blocking)
    assert any("Boyut özelliği" in u for u in uyarilar)

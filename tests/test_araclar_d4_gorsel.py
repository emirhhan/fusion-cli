"""Görsel işleme P2 düzeltmeleri (T1-30, T1-31)."""

from __future__ import annotations

import pytest
from PIL import Image

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.image_ops import optimize_image


@pytest.fixture
def context(tmp_path):
    return ToolContext(root=tmp_path)


def _saydam_png(yol, boyut=(40, 20)):
    Image.new("RGBA", boyut, (255, 0, 0, 0)).save(yol)


def test_saydam_png_webp_ye_cevrilince_alfa_korunur(context, tmp_path):
    """T1-30: WebP alfa destekler; saydam logo siyah/kaynak zeminle kaydedilmemeli."""
    _saydam_png(tmp_path / "logo.png")

    sonuc = optimize_image({"path": "logo.png"}, context)

    assert sonuc.ok, sonuc.output
    with Image.open(tmp_path / "logo.webp") as cikti:
        assert "A" in cikti.mode
        assert cikti.convert("RGBA").getpixel((0, 0))[3] == 0


def test_saydam_png_jpeg_e_cevrilince_beyaz_zemin(context, tmp_path):
    """JPEG alfa taşıyamaz; saydam alan siyah değil BEYAZ zemin olur."""
    _saydam_png(tmp_path / "logo.png")

    sonuc = optimize_image({"path": "logo.png", "out": "logo.jpg"}, context)

    assert sonuc.ok, sonuc.output
    with Image.open(tmp_path / "logo.jpg") as cikti:
        assert min(cikti.convert("RGB").getpixel((5, 5))) > 240


def test_kirpma_ve_buyutme_sonucta_acikca_yazilir(context, tmp_path):
    """T1-31a: başlık sözleşmesi "kırpma/büyütme AÇIKÇA söylenir" diyordu; söylenmiyordu."""
    Image.new("RGB", (100, 50), "blue").save(tmp_path / "k.png")

    sonuc = optimize_image({"path": "k.png", "width": 200, "height": 200}, context)

    assert sonuc.ok, sonuc.output
    assert "kırpıldı" in sonuc.output and "büyütüldü" in sonuc.output


def test_metin_olcu_kabul_edilir(context, tmp_path):
    """T1-31c: width "80" metni sessizce yok sayılıp yalnız biçim çevrilmemeli."""
    Image.new("RGB", (160, 160), "blue").save(tmp_path / "k.png")

    sonuc = optimize_image({"path": "k.png", "width": "80", "height": "80.0"}, context)

    assert sonuc.ok, sonuc.output
    with Image.open(tmp_path / "k.webp") as cikti:
        assert cikti.size == (80, 80)


def test_tek_olcu_verilirse_yok_sayildigi_soylenir(context, tmp_path):
    Image.new("RGB", (160, 160), "blue").save(tmp_path / "k.png")

    sonuc = optimize_image({"path": "k.png", "width": 80}, context)

    assert sonuc.ok and "height" in sonuc.output and "yok sayıldı" in sonuc.output


def test_bozuk_gorsel_istisna_degil_hata_doner(context, tmp_path):
    """T1-31d: Pillow'un ValueError/SyntaxError'u yakalama listesinden kaçıyordu."""
    (tmp_path / "bozuk.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40)

    sonuc = optimize_image({"path": "bozuk.png"}, context)

    assert not sonuc.ok and "Görsel işlenemedi" in sonuc.output


def test_ezilen_hedef_geri_alinabilir(context, tmp_path):
    """T1-31b: aynı uzantıya çevirmede orijinal ezilir; geri alma kaydı olmalı."""
    hedef = tmp_path / "x.webp"
    Image.new("RGB", (30, 30), "blue").save(hedef)
    orijinal = hedef.read_bytes()

    sonuc = optimize_image({"path": "x.webp"}, context)

    assert sonuc.ok, sonuc.output
    context.changes.restore()
    assert hedef.read_bytes() == orijinal

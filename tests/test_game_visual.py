"""Oyunun ekran görüntüsünden ölçülen görsel kusurlar (`game_visual`).

Ölçüldü (6 Ekim 2026, dalga24 "zor oyun"): denetçi 7/8 verdi, kullanıcı "rezalet"
dedi. Görüntüde: oyun alanı yalnız sol üst çeyrek (gerisi açık ızgara), oyuncu silinmeyen
iz bırakıyor, 6 sn'de hiç düşman yok, HUD açık zeminde soluk. Hiçbiri ölçülmüyordu.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from fusion_cli.tools.game_visual import (
    contrast_ratio,
    idle_motion_problem,
    partial_fill_problem,
    trail_problem,
)


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _sahne(kare: int, *, iz: bool, zemin=(20, 24, 40)) -> bytes:
    """Sağa giden 20 px'lik oyuncu; iz=True ise önceki konumlar silinmez."""
    image = Image.new("RGB", (400, 300), zemin)
    draw = ImageDraw.Draw(image)
    for adim in range(kare + 1) if iz else (kare,):
        x = 40 + adim * 40
        draw.rectangle((x, 140, x + 20, 160), fill=(0, 230, 120))
    return _png(image)


def test_ceyrek_ekran_cizimi_yakalanir_tam_ekran_gecer():
    bozuk = Image.new("RGB", (400, 300), (240, 240, 245))
    ImageDraw.Draw(bozuk).rectangle((0, 0, 199, 149), fill=(10, 10, 16))
    for x in range(0, 400, 20):  # açık bölgede ızgara çizgileri
        ImageDraw.Draw(bozuk).line((x, 150, x, 300), fill=(225, 225, 232))
    assert partial_fill_problem(_png(bozuk)) is not None
    assert partial_fill_problem(_sahne(0, iz=False)) is None


def test_silinmeyen_iz_yakalanir_temiz_hareket_gecer():
    izli = [_sahne(i, iz=True) for i in range(5)]
    temiz = [_sahne(i, iz=False) for i in range(5)]
    assert trail_problem(izli) is not None
    assert trail_problem(temiz) is None


def test_kendiliginden_hicbir_sey_kipirdamiyorsa_soylenir():
    sabit = _sahne(0, iz=False)
    assert idle_motion_problem([sabit, sabit, sabit]) is not None
    assert idle_motion_problem([_sahne(0, iz=False), _sahne(2, iz=False)]) is None


def test_kontrast_orani_wcag_ile_ayni():
    assert round(contrast_ratio((0, 0, 0), (255, 255, 255)), 1) == 21.0
    assert contrast_ratio((200, 200, 205), (240, 240, 245)) < 3


def test_yuklenen_gorsellerin_cogu_hic_cizilmezse_sorun_sayilir():
    """Ölçüldü (8 Ekim, dalga41): 10 sprite yüklendi, 3'ü çizildi; düşmanlar ekranda düz
    daire olarak çiziliyordu (kod `chaser` arıyor, görsel `enemy_chaser` adıyla kayıtlı)."""
    from fusion_cli.tools.game_assets import AssetUsage

    yuklenen = tuple(f"assets/s{i}.svg" for i in range(10))
    assert AssetUsage(yuklenen, yuklenen[:3]).problem is not None
    # Boss/güçlendirme gibi az sayıda görselin kısa denemede çıkmaması normaldir.
    assert AssetUsage(yuklenen, yuklenen[:6]).problem is None
    assert AssetUsage(yuklenen[:2], ()).problem is None

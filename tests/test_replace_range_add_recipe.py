"""`replace_range` aralığı SİLER; açıklamasının verdiği ekleme tarifi çalışmalı.

Ölçüldü (7 Eylül, `mevcut-projeye-uy`): görev "projeye cikar() ekle" idi. Model
`topla`nın satır aralığını seçip yerine yalnız `cikar`ı yazdı — `topla` silindi ve
görev düştü. Sebep araç değil AÇIKLAMAYDI: "Eski içeriği gönderme" cümlesi
DEĞİŞTİRME için doğru, EKLEME için yanıltıcıydı.

Bu dosya iki şeyi birlikte kilitler: aracın silme semantiği ve açıklamada verilen
ekleme tarifinin gerçekten işe yaradığı. Tarif yanlış olsaydı model onu izleyip
yine kod silerdi.
"""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry
from fusion_cli.tools.files import read_file, replace_range

KAYNAK = '"""Matematik yardimcilari."""\n\n\ndef topla(a, b):\n    return a + b\n'


def _baglam(tmp_path):
    baglam = ToolContext(tmp_path)
    (tmp_path / "matematik.py").write_text(KAYNAK, encoding="utf-8")
    read_file({"path": "matematik.py"}, baglam)
    return baglam


def test_araligi_yalniz_yeni_icerikle_degistirmek_eski_kodu_siler(tmp_path):
    """Ölçülen hatanın kendisi: davranış doğru, model beklentisi yanlıştı."""
    baglam = _baglam(tmp_path)

    replace_range(
        {
            "path": "matematik.py",
            "start_line": 4,
            "end_line": 5,
            "new": "def cikar(a, b):\n    return a - b",
        },
        baglam,
    )

    sonuc = (tmp_path / "matematik.py").read_text(encoding="utf-8")
    assert "def topla" not in sonuc, "aralık silinmiyorsa bu testin gerekçesi kalmaz"


def test_aciklamadaki_ekleme_tarifi_var_olan_kodu_korur(tmp_path):
    """Tarif: son satırı aralığa al, `new` içinde AYNEN tekrar et, altına ekle."""
    baglam = _baglam(tmp_path)

    replace_range(
        {
            "path": "matematik.py",
            "start_line": 5,
            "end_line": 5,
            "new": "    return a + b\n\n\ndef cikar(a, b):\n    return a - b",
        },
        baglam,
    )

    sonuc = (tmp_path / "matematik.py").read_text(encoding="utf-8")
    assert "def topla" in sonuc
    assert "def cikar" in sonuc


def test_arac_aciklamasi_ekleme_tuzagini_soyler():
    """Modele sunulan metin tuzağı SÖYLEMELİ; yoksa aynı hata tekrarlanır."""
    arac = build_registry().get("replace_range")

    assert arac is not None
    metin = arac.description + str(arac.parameters)
    assert "SİLİNİR" in metin or "silinir" in metin
    assert "EKLEME" in metin or "ekleme" in metin

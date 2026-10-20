"""Geliştirme isteği "salt okuma" sanılmamalı.

Ölçüldü (29 Eylül): "projesini tam anlamıyla geliştir ... her şeyi oku ne işe
yaradığını anla ... ayarla ... UI'a sahip olsun istiyorum ... bir fonksiyon daha
istiyorum" görevi yalnız "proje ... oku" kalıbına uyduğu için `workspace_read`
sayıldı; yazma araçları kapatıldı, model dört koşu boyunca tek dosya yazamadı.
"""

from __future__ import annotations

import pytest

from fusion_cli.engines.effects.detect import required_effect_for

MUTASYON = "workspace_mutation"


@pytest.mark.parametrize(
    "gorev",
    [
        (
            "ornek proje projesini tam anlamıyla geliştir çok profesyonel bir hale gelmiş "
            "olsun bu projedeki her işi her şeyi oku ne işe yaradığını anla"
        ),
        "mcp sunucusu falan ne ayarlaman lazımsa ayarla",
        "görünüm olarak da APPLE benzeri bir UI a sahip olsun istiyorum",
        "örnek olarak bir fonksiyon daha istiyorum otomatik story",
        "giriş sayfasını iyileştir",
        "bu özelliği projeye uygula",
    ],
)
def test_gelistirme_istegi_degisiklik_sayilir(gorev):
    assert required_effect_for(gorev) == MUTASYON


@pytest.mark.parametrize(
    ("gorev", "beklenen"),
    [
        ("projedeki dosyaları oku ve listele", "workspace_read"),
        ("merhaba nasılsın", None),
    ],
)
def test_salt_okuma_ve_sohbet_etkilenmez(gorev, beklenen):
    assert required_effect_for(gorev) == beklenen


@pytest.mark.parametrize(
    "gorev",
    [
        "uygulamanın ayarlarını göster",
        "geliştirme ortamı nedir",
        "bu uygulama ne işe yarıyor",
    ],
)
def test_isim_olarak_gecen_fiil_kokleri_degisiklik_sayilmaz(gorev):
    assert required_effect_for(gorev) != MUTASYON

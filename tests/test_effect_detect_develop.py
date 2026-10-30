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


# --- E1-07: isim olan sözcükler olumsuzlama sayılmaz -------------------------------------


@pytest.mark.parametrize(
    "gorev",
    [
        "Arama kutusu ekle",
        "yükleme ekranı oluştur",
        "araştırma sayfası yaz",
        "Hero bölümüne arama kutusu ekle, edit_file kullan",
        "a.py dosyası oluştur ama silme lütfen",
    ],
)
def test_isim_olarak_gecen_sozcuk_mutasyon_kapisini_kapatmaz(gorev):
    from fusion_cli.engines.effects.detect import required_effect_for

    assert required_effect_for(gorev) is not None


@pytest.mark.parametrize(
    "gorev",
    ["dosyayı silme", "a.py dosyası oluşturma", "Dosya oluşturma lütfen", "lütfen yapma"],
)
def test_fiil_kipindeki_olumsuz_emir_mutasyon_istemez(gorev):
    from fusion_cli.engines.effects.detect import required_effect_for

    assert required_effect_for(gorev) is None


# --- Dalga 4: büyük harfli Türkçe girdi kalıpları bozmaz (E1-12) ----------------- #


def test_buyuk_harfli_turkce_gorev_mutasyon_sayilir():
    """Ölçüldü (30 Ekim): 'DOSYAYI SİL' → `İ`.lower() iki karakter olduğundan None dönüyordu."""
    from fusion_cli.engines.effects.detect import required_effect_for
    from fusion_cli.engines.effects.model import EffectKind  # noqa: F401

    assert required_effect_for("DOSYAYI SİL") == required_effect_for("dosyayı sil")
    assert required_effect_for("DÜZELT İNDEX.HTML") == required_effect_for("düzelt index.html")
    assert required_effect_for("DOSYAYI SİL") is not None


def test_buyuk_harfli_ingilizce_gorev_bozulmaz():
    from fusion_cli.engines.effects.detect import required_effect_for

    assert required_effect_for("FIX THE BUG IN app.py") == required_effect_for(
        "fix the bug in app.py"
    )


def test_ortak_kucultme_dotted_i_yi_tek_karaktere_indirir():
    from fusion_cli.core.text_fold import lower_tr_aware

    assert lower_tr_aware("SİL") == "sil"
    assert lower_tr_aware("İSTEK") == "istek"
    assert lower_tr_aware("INDEX") == "index"
    assert lower_tr_aware("kız") == "kız"

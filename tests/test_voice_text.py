"""Seslendirilecek metnin hazırlanması.

Fusion'ın cevabı markdown, dosya yolu, kod ve sayı doludur. Ham hâliyle
okunursa hangi model kullanılırsa kullanılsın kulağa berbat gelir: yıldızlar,
ters tırnaklar ve eğik çizgiler tek tek telaffuz edilir. Bu katman modelden
BAĞIMSIZDIR; daha iyi bir modele geçilse de gerekir.
"""

from __future__ import annotations

import pytest

from fusion_cli.appserver.voice_text import prepare_speech, split_sentences


def test_markdown_isaretleri_okunmaz():
    assert "*" not in prepare_speech("**Testler** geçti")
    assert "`" not in prepare_speech("`app.py` dosyası")
    assert "#" not in prepare_speech("# Başlık")


def test_kod_blogu_hic_okunmaz():
    """Kod bloğunu seslendirmek dakikalarca anlamsız hece üretir."""
    metin = "Şunu ekledim:\n```python\ndef f():\n    return 1\n```\nTamamdır."
    hazir = prepare_speech(metin)

    assert "def" not in hazir
    assert "return" not in hazir
    assert "Tamamdır" in hazir
    assert "kod bloğu" in hazir.casefold()


def test_dosya_yolu_okunabilir_hale_gelir():
    hazir = prepare_speech("app/src/screens/Composer.tsx dosyasını değiştirdim")

    assert "/" not in hazir
    assert "Composer" in hazir
    # Uzantı harf harf değil, okunabilir biçimde verilir.
    assert ".tsx" not in hazir


def test_sayilar_ve_birimler_turkce_okunur():
    assert "yüzde" in prepare_speech("%92 başarı")
    assert "megabayt" in prepare_speech("60MB indirildi")
    assert "saniye" in prepare_speech("2.4s sürdü")
    assert "bölü" in prepare_speech("169/169 test geçti")


def test_cumlelere_bolunur_ve_bos_parca_uretmez():
    parcalar = split_sentences("Bir. İki! Üç? Dört...")

    assert len(parcalar) == 4
    assert all(p.strip() for p in parcalar)


def test_asiri_uzun_metin_kesilir_ve_kesildigi_soylenir():
    uzun = "Cümle. " * 5_000
    hazir = prepare_speech(uzun)

    assert len(hazir) <= 4_200
    assert "kısalt" in hazir.casefold()


def test_bos_metin_cokertmez():
    assert prepare_speech("") == ""
    assert prepare_speech("```\nsadece kod\n```").strip() != ""


@pytest.mark.parametrize("giris", ["", "   ", "\n\n"])
def test_bosluktan_ibaret_metin_bos_doner(giris: str):
    assert prepare_speech(giris) == ""

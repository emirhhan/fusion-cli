"""Seslendirilecek metnin hazırlanması.

Fusion'ın cevabı markdown, dosya yolu, kod ve sayı doludur. Ham hâliyle
okunursa hangi model kullanılırsa kullanılsın kulağa berbat gelir: yıldızlar,
ters tırnaklar ve eğik çizgiler tek tek telaffuz edilir. Bu katman modelden
BAĞIMSIZDIR; daha iyi bir modele geçilse de gerekir.
"""

from __future__ import annotations

import pytest

from fusion_cli.appserver.voice_text import prepare_speech, split_sentences


@pytest.mark.parametrize(
    "emoji", ["😀", "👍🏽", "👨‍👩‍👧‍👦", "🇹🇷", "❤️", "1️⃣", "✅", "©️", "⬆️", "↔️", "‼️"]
)
def test_emojis_are_not_spoken(emoji):
    assert prepare_speech(f"Merhaba {emoji} dünya.") == "Merhaba dünya."
    assert prepare_speech(emoji) == ""


def test_emoji_cleaning_preserves_numbers_turkish_and_math():
    assert prepare_speech("3 + 2 = 5. Çığ, öğün!") == "3 + 2 = 5. Çığ, öğün!"
    assert prepare_speech("⌈3⌉ + ⌊2⌋ = 5") == "⌈3⌉ + ⌊2⌋ = 5"


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


def test_binlik_ayraci_tarih_surum_ve_baglanti_bozulmaz() -> None:
    """Ölçüldü (30 Ekim, S2-32): "1.000" → "1 virgül 000", "25.10.2026" → "25.10 virgül 2026",
    "https://a.com/x/y" → "https: y" okunuyordu."""
    assert prepare_speech("1.000 dosya") == "1000 dosya"
    assert prepare_speech("12.500.000 TL") == "12500000 TL"
    assert "virgül" not in prepare_speech("25.10.2026 tarihinde")
    assert "virgül" not in prepare_speech("sürüm 3.11.2 çıktı")
    assert prepare_speech("bkz https://a.com/x/y sayfası") == "bkz a.com sayfası"
    assert "2 virgül 4" in prepare_speech("2,4 saniye")  # gerçek ondalık korunur

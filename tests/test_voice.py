"""Sesli yanıtın sözleşmesi.

Fusion'ın konuşması BEDAVA ve ÇEVRİMDIŞI olmalı: işletim sisteminin kendi
sentezleyicisi kullanılır. macOS'ta `say`, Windows'ta PowerShell. Model
indirme, API anahtarı ve ağ erişimi YOKTUR.
"""

from __future__ import annotations

import pytest

from fusion_cli.appserver.voice import speak_argv, turkish_voice


def test_macos_turkce_sesle_konusur():
    """macOS'ta Türkçe ses `Yelda`dır ve sistemde kuruludur (ölçüldü)."""
    argv = speak_argv("Darwin", "Merhaba", voice="Yelda")

    assert argv[0] == "say"
    assert "-v" in argv and "Yelda" in argv
    assert argv[-1] == "Merhaba"


def test_windows_powershell_sentezleyicisini_kullanir():
    argv = speak_argv("Windows", "Merhaba", voice=None)

    assert argv[0].casefold().startswith("powershell")
    birlesik = " ".join(argv)
    assert "SpeechSynthesizer" in birlesik
    assert "Merhaba" in birlesik


def test_desteklenmeyen_platform_sessizce_gecilmez():
    with pytest.raises(ValueError):
        speak_argv("Linux", "Merhaba", voice=None)


def test_metin_kabuga_kacis_karakteri_sizdirmaz():
    """Metin kullanıcıdan/modelden gelir; komut enjeksiyonuna kapalı olmalı."""
    argv = speak_argv("Darwin", 'ba"; rm -rf /; echo "', voice="Yelda")

    # Argüman listesi kabuktan geçmez; metin TEK argüman olarak kalır.
    assert argv[-1] == 'ba"; rm -rf /; echo "'
    assert len(argv) == 4


def test_turkce_ses_secimi_kurulu_olanlardan_yapilir():
    """Ses adı uydurulmaz: sistemde kurulu Türkçe seslerden seçilir."""
    assert turkish_voice(("Yelda tr_TR", "Alex en_US")) == "Yelda"
    assert turkish_voice(("Alex en_US",)) is None


def test_en_iyi_ses_secilir_compact_son_caredir():
    """Ses seçimi KALİTEYE göre yapılır; ilk bulunan alınmaz.

    Apple'ın `voice.compact` ailesi en düşük kademedir ve robotik duyulur —
    kullanıcı bunu bildirdi. `ttsbundle`/`premium`/`enhanced` aileleri belirgin
    biçimde daha doğaldır ve ücretsiz indirilebilir. Kurulu en iyi ses seçilir;
    compact yalnız başka seçenek yoksa kullanılır.
    """
    from fusion_cli.appserver.voice import best_voice

    kurulu = (
        ("Yelda", "tr-TR", "com.apple.voice.compact.tr-TR.Yelda"),
        ("Cem", "tr-TR", "com.apple.ttsbundle.Cem"),
    )
    assert best_voice(kurulu) == "Cem"

    yalniz_compact = (("Yelda", "tr-TR", "com.apple.voice.compact.tr-TR.Yelda"),)
    assert best_voice(yalniz_compact) == "Yelda"

    assert best_voice(()) is None


def test_daha_iyi_ses_kuruluysa_kullanici_bilgilendirilir():
    """Daha iyi ses varken sessizce kötüsüyle konuşmak yanlış olurdu."""
    from fusion_cli.appserver.voice import upgrade_hint

    yalniz_compact = (("Yelda", "tr-TR", "com.apple.voice.compact.tr-TR.Yelda"),)
    ipucu = upgrade_hint(yalniz_compact)
    assert ipucu is not None and "Cem" in ipucu

    iyi_ses_var = (("Cem", "tr-TR", "com.apple.ttsbundle.Cem"),)
    assert upgrade_hint(iyi_ses_var) is None

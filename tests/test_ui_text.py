"""Görüntülenecek metin dönüşümleri — model kimliğinin okunur biçimi."""

from __future__ import annotations

from fusion_cli.ui.text import format_model


def test_uc_parcali_kimlikte_aradaki_satici_atilir():
    """`nvidia_nim/nvidia/…` — satıcı adı yer kaplamaktan başka bir şey yapmaz."""
    assert (
        format_model("nvidia_nim/nvidia/nemotron-3-super-120b-a12b")
        == "nvidia_nim/nemotron-3-super-120b-a12b"
    )


def test_saglayici_oneki_korunur():
    """Yedek çoğu zaman AYNI modelin başka sağlayıcıdaki kopyasıdır.

    Önek atılsaydı yedeğe düşmüş bir tur birincille aynı görünür ve Faz 1'de
    düzeltilen hata gözle fark edilemez hâle gelirdi.
    """
    nim = format_model("nvidia_nim/nvidia/nemotron-3-super-120b-a12b")
    openrouter = format_model("openrouter/nvidia/nemotron-3-super-120b-a12b:free")

    assert nim != openrouter
    assert openrouter.startswith("openrouter/")


def test_iki_parcali_kimlik_oldugu_gibi_kalir():
    assert format_model("ollama/qwen2.5-coder:7b") == "ollama/qwen2.5-coder:7b"


def test_saglayicisiz_kimlik_bozulmaz():
    """Beklenmedik biçim ekrandan bir şey EKSİLTMEMELİ."""
    assert format_model("yalnizca-model") == "yalnizca-model"

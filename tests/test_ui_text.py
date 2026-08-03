"""Görüntülenecek metin dönüşümleri — model kimliğinin okunur biçimi."""

from __future__ import annotations

from fusion_cli.ui.text import format_model, segment, strip_thinking


def test_segment_gorunur_ve_dusunme_parcalarina_ayirir():
    parts = segment("onsoz <think>gizli</think>sonrasi")

    assert [(p.is_thinking, p.text) for p in parts] == [
        (False, "onsoz "),
        (True, "gizli"),
        (False, "sonrasi"),
    ]


def test_segment_akista_yarim_etiketi_geri_tutar():
    """`<th` sona gelirse görünür kısımda sızmaz; akış bitince serbest kalır."""
    tutulan = segment("abc<th", streaming=True)
    serbest = segment("abc<th", streaming=False)

    assert [(p.is_thinking, p.text) for p in tutulan] == [(False, "abc")]
    assert [(p.is_thinking, p.text) for p in serbest] == [(False, "abc<th")]


def test_strip_thinking_segment_uzerinden_tutarli():
    """Aynı gramerden beslendiği için ikisi aynı görünür metni verir."""
    ham = "onsoz <think>ara</think>sonrasi"
    gorunur = "".join(p.text for p in segment(ham) if not p.is_thinking)

    assert strip_thinking(ham) == gorunur == "onsoz sonrasi"


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

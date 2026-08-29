"""Cevabı hangi kademe yazdıysa kullanıcı onu GÖRÜR.

Ölçüldü: oturumu düşmüş bir Gemini profiliyle yapılan canlı koşuda cevabı anonim
"Flash-Lite" kademesi yazdı; ekranda ise yalnızca `gemini_web/auto` görünüyordu.
Kullanıcının kendi Pro hesabının gücüyle çalıştığını sanması için hiçbir engel
yoktu. İstenen kimlik ile gözlenen kademe ayrışabildiğine göre, satır ikisini de
söylemelidir.
"""

from __future__ import annotations

from fusion_cli.core.types import ModelResult
from fusion_cli.ui.text import format_model, format_served_model


def _sonuc(model: str, served_by: str) -> ModelResult:
    return ModelResult(name=model, model=model, text="", latency_ms=1, ok=True, served_by=served_by)


def test_gozlenen_kademe_satira_eklenir() -> None:
    satir = format_served_model("gemini_web/isimdijital/auto", "Flash-Lite")

    assert satir == "gemini_web/isimdijital · Flash-Lite"


def test_web_oturumunda_hesap_adi_gizlenmez() -> None:
    """Ölçüldü: kullanıcı `gemini_web/auto` satırını AYRI BİR SAĞLAYICI sandı.

    Orta parça LiteLLM kimliklerinde satıcı adıdır ve gürültüdür; web
    oturumlarında ise hesap adıdır ve hangi hesapla çalışıldığını söyleyen tek
    bilgidir. Son parça web oturumlarında her zaman "auto"dur, hiçbir şey söylemez.
    """
    assert format_model("gemini_web/isimdijital/auto") == "gemini_web/isimdijital"
    assert format_model("chatgpt_web/main/auto") == "chatgpt_web/main"


def test_litellm_kimliginde_satici_adi_hala_atilir() -> None:
    """Web olmayan kimliklerde davranış DEĞİŞMEZ."""
    assert format_model("nvidia_nim/nvidia/nemotron-3-ultra") == "nvidia_nim/nemotron-3-ultra"
    assert format_model("openrouter/nvidia/nemotron:free") == "openrouter/nemotron:free"
    assert format_model("gpt-4o") == "gpt-4o"


def test_kademe_bilinmiyorsa_satir_degismez() -> None:
    """Uydurulmuş bir kademe, kademe yokluğundan kötüdür."""
    assert format_served_model("gemini_web/isimdijital/auto", "") == format_model(
        "gemini_web/isimdijital/auto"
    )
    assert format_served_model("gemini_web/isimdijital/auto", "   ") == "gemini_web/isimdijital"


def test_kademe_kimlikte_zaten_varsa_tekrarlanmaz() -> None:
    assert format_served_model("nvidia_nim/nvidia/nemotron-3-ultra", "nemotron-3-ultra") == (
        "nvidia_nim/nemotron-3-ultra"
    )


def test_sonuc_kademeyi_tasir() -> None:
    """`served_by` sonuç nesnesinde taşınmazsa sunum katmanı onu hiç göremez."""
    assert _sonuc("gemini_web/main/auto", "2.5 Pro").served_by == "2.5 Pro"
    assert ModelResult(name="x", model="x", text="", latency_ms=0, ok=True).served_by == ""

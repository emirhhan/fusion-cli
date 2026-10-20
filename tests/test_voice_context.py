"""Sesli tur protokolü kullanıcı sözünü ve bağlamını ayırır."""

from __future__ import annotations

import pytest

from fusion_cli.appserver.voice_context import parse_voice_context


@pytest.mark.parametrize("value", [True, "sesli", [], {"kesilen": None}, {"talimat": "x"}])
def test_gecersiz_sesli_baglam_reddedilir(value):
    with pytest.raises(ValueError, match="Sesli konuşma bağlamı geçersiz"):
        parse_voice_context(value)


def test_yazili_tur_baglam_tasimaz():
    assert parse_voice_context(None) is None


def test_sesli_tur_kesilmeden_de_kendi_yonergesini_tasir():
    context = parse_voice_context({})
    assert context is not None
    assert "Türkçe, doğal ve doğrudan" in context.prompt()


def test_iki_sesli_turun_kesilme_bilgisi_birbirine_sizmaz():
    first = parse_voice_context({"kesilen": 'İlk "seçenek"\nAlıntı'})
    second = parse_voice_context({"kesilen": "İkinci seçenek"})
    assert first is not None and second is not None
    assert r"\"seçenek\"\nAlıntı" in first.prompt()
    assert "İkinci seçenek" not in first.prompt()
    assert "İlk" not in second.prompt()

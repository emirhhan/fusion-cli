"""Güvenli sıkıştırma kod bloğunu ve araç çıktısını bozmaz (C1-26)."""

from __future__ import annotations

from fusion_cli.core.compression import compress_messages, compress_text
from fusion_cli.core.types import Message


def test_duz_metnin_satir_sonu_bosluklari_ve_fazla_bos_satirlari_kirpilir() -> None:
    assert compress_text("a  \nb\n\n\n\nc") == "a\nb\n\nc"


def test_cit_icindeki_kod_aynen_korunur() -> None:
    kod = "```python\nx = '''a  \n\n\n\nb'''  \n```"
    metin = f"önce  \n\n\n\n{kod}\n\n\n\nsonra  "

    sonuc = compress_text(metin)

    assert kod in sonuc
    assert sonuc.startswith("önce\n\n```") and sonuc.endswith("```\n\nsonra")


def test_kapanmamis_cit_sona_kadar_korunur() -> None:
    sonuc = compress_text("giriş  \n```\nkod  \n\n\n\nson")

    assert sonuc == "giriş\n```\nkod  \n\n\n\nson"


def test_arac_mesajina_dokunulmaz() -> None:
    arac = Message("tool", "satır  \n\n\n\nsonu", tool_call_id="1", name="read_file")
    kullanici = Message("user", "merhaba  \n\n\n\ndünya")

    sonuc = compress_messages([arac, kullanici])

    assert sonuc[0].content == arac.content
    assert sonuc[1].content == "merhaba\n\ndünya"

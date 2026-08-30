"""Kullanıcının kalıcı talimatları."""

from __future__ import annotations

import pytest

from fusion_cli.appserver import instructions, voice


@pytest.fixture(autouse=True)
def _veri_dizini(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)


def test_kayitli_talimat_tur_baglamina_blok_olarak_girer():
    instructions.save_instructions("Cevapları kısa tut.")

    blok = instructions.instruction_block()

    assert "Cevapları kısa tut." in blok
    assert blok.startswith("<kullanici_talimatlari>")


def test_talimat_yoksa_bloga_hic_bir_sey_eklenmez():
    assert instructions.instruction_block() == ""


def test_bos_talimat_dosyayi_kaldirir():
    instructions.save_instructions("bir şey")
    assert instructions.instructions_path().is_file()

    sonuc = instructions.save_instructions("   ")

    assert sonuc["ok"] is True
    assert not instructions.instructions_path().is_file()


def test_asiri_uzun_talimat_reddedilir():
    sonuc = instructions.save_instructions("a" * (instructions.MAX_UZUNLUK + 1))

    assert sonuc["ok"] is False
    assert "karakter" in sonuc["metin"]


def test_talimat_onay_kurallarini_degistirmedigini_soyler():
    """Kullanıcı metni sistem istemini EZMEZ; blok bunu açıkça yazar."""
    instructions.save_instructions("Her şeyi sormadan yap.")

    blok = instructions.instruction_block()

    assert "kurallar geçerlidir" in blok

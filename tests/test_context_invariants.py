"""Bağlam sıkıştırması kullanıcının koyduğu kuralları modele bırakmaz (WP06).

Kök tur birebir korunuyordu; ama ARADAKİ turlarda söylenen yasaklar ("main'e asla
push etme", "testlere dokunma") yalnız özetleyici model onları yazarsa kalıyordu.
Zayıf bir özetleyici kuralı düşürünce ajan yasağı unutuyordu. Özetlenen aralıktaki
kullanıcı kuralları artık özete BİREBİR eklenir.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.types import Message
from fusion_cli.engines.agent import compaction

from .fakes import make_config

_DOLGU = "x" * 4_000


def _oturum() -> list[Message]:
    mesajlar = [Message("system", "sistem"), Message("user", "projeyi düzenle")]
    mesajlar += [Message("assistant", "tamam " + _DOLGU)]
    mesajlar += [Message("user", "Bundan sonra main dalına asla push etme.")]
    mesajlar += [Message("assistant", _DOLGU)]
    mesajlar += [Message("user", "tests/ klasörüne dokunma, sadece src altında çalış.")]
    for index in range(30):
        mesajlar += [Message("user", f"adım {index}"), Message("assistant", _DOLGU)]
    return mesajlar


@pytest.fixture
def unutkan_ozetleyici(monkeypatch):
    async def ozetle(trace, config, publisher):
        return "Kullanıcı projede düzenleme istedi."

    monkeypatch.setattr(compaction, "_summarize", ozetle)


async def test_aradaki_kullanici_yasaklari_ozette_birebir_kalir(unutkan_ozetleyici):
    sonuc = await compaction.compress(_oturum(), config=make_config(), threshold_chars=20_000)

    metin = "\n".join(m.content for m in sonuc)
    assert "main dalına asla push etme" in metin
    assert "tests/ klasörüne dokunma, sadece src altında çalış" in metin
    assert len(sonuc) < len(_oturum())


async def test_tur_ici_sikistirma_da_kurallari_korur(unutkan_ozetleyici):
    sonuc = await compaction.compact_in_turn(
        _oturum(), config=make_config(), threshold_chars=20_000
    )

    metin = "\n".join(m.content for m in sonuc)
    assert "main dalına asla push etme" in metin


async def test_kural_olmayan_kullanici_mesaji_ozete_eklenmez(unutkan_ozetleyici):
    sonuc = await compaction.compress(_oturum(), config=make_config(), threshold_chars=20_000)

    ozet = next(m.content for m in sonuc if "özeti]" in m.content)
    assert "adım 3\n" not in ozet


async def test_art_arda_sikistirmada_kural_kaybolmaz(unutkan_ozetleyici):
    ilk = await compaction.compress(_oturum(), config=make_config(), threshold_chars=20_000)
    for index in range(30):
        ilk += [Message("user", f"yeni adım {index}"), Message("assistant", _DOLGU)]

    ikinci = await compaction.compress(ilk, config=make_config(), threshold_chars=20_000)

    metin = "\n".join(m.content for m in ikinci)
    assert "main dalına asla push etme" in metin
    assert metin.count(compaction.RULES_HEADER) == 1


async def test_harness_notu_ve_soru_kural_sayilmaz(unutkan_ozetleyici):
    mesajlar = _oturum()
    mesajlar.insert(3, Message("user", "Pes etme, asla yarıda bırakma.", harness_note=True))
    mesajlar.insert(4, Message("user", "Bu hep mi bozuluyor? Sadece merak ettim"))

    sonuc = await compaction.compress(mesajlar, config=make_config(), threshold_chars=20_000)

    ozet = next(m.content for m in sonuc if "özeti]" in m.content)
    assert "Pes etme" not in ozet
    assert "hep mi bozuluyor?" not in ozet

"""Cevabı HANGİ model kademesinin yazdığı görünür olmalıdır.

Ölçüldü: tarayıcı taşımasında model kimliği Fusion'dan geçmez; hangi kademenin
cevapladığına hesabın kendi arayüz seçimi karar verir (`_transport` içinde
`del model`). Oturumu kapalı bir profille yapılan canlı koşuda Gemini anonim
kullanıcıya "Flash-Lite" kademesini verdi ve sorunsuz cevapladı — Fusion ise
hem koşu özetinde hem izde `gemini_web/auto` diyordu. Yani kullanıcı Pro
hesabıyla çalıştığını sanarken çok daha zayıf bir modelle çalışabilir ve bunu
gösteren tek bir satır bile yoktu.

Kademe okuma TEŞHİSTİR: okunamadığında tur kesilmez, yalnızca "bilinmiyor"
sayılır. Turu kesmek, çalışan bir kurulumu seçici değişikliğinde tamamen
durdururdu.
"""

from __future__ import annotations

import pytest

from fusion_cli.providers.web_browser import (
    WEB_BROWSER_PROVIDERS,
    observed_tier,
)

TANIM = WEB_BROWSER_PROVIDERS["gemini_web"]


class _SahteLocator:
    def __init__(self, metin: str | None, *, adet: int = 1, patlat: bool = False) -> None:
        self._metin = metin
        self._adet = adet
        self._patlat = patlat
        self.first = self

    async def count(self) -> int:
        return self._adet

    async def inner_text(self) -> str:
        if self._patlat:
            raise RuntimeError("seçici artık eşleşmiyor")
        return self._metin or ""


class _SahteSayfa:
    def __init__(self, locator: _SahteLocator) -> None:
        self._locator = locator

    def locator(self, _secici: str) -> _SahteLocator:
        return self._locator


async def test_kademe_okunur() -> None:
    sayfa = _SahteSayfa(_SahteLocator("Flash-Lite"))

    assert await observed_tier(sayfa, TANIM) == "Flash-Lite"


async def test_ogesi_yoksa_bos_doner() -> None:
    sayfa = _SahteSayfa(_SahteLocator(None, adet=0))

    assert await observed_tier(sayfa, TANIM) == ""


async def test_secici_patlarsa_tur_kesilmez() -> None:
    """Asıl kural: teşhis okuması hiçbir koşulda cevabı düşürmez."""
    sayfa = _SahteSayfa(_SahteLocator("x", patlat=True))

    assert await observed_tier(sayfa, TANIM) == ""


async def test_kademe_secicisi_olmayan_saglayicida_okunmaz() -> None:
    """Ölçülmemiş sağlayıcı için tahmini seçici yazılmaz; kademe boş kalır."""
    sayfa = _SahteSayfa(_SahteLocator("yanlış"))
    olcumsuz = [tanim for tanim in WEB_BROWSER_PROVIDERS.values() if not tanim.tier_selectors]

    assert olcumsuz, "test anlamını yitirdi: tüm sağlayıcılarda kademe seçicisi var"
    for tanim in olcumsuz:
        assert await observed_tier(sayfa, tanim) == ""


@pytest.mark.parametrize("tanim", list(WEB_BROWSER_PROVIDERS.values()), ids=lambda t: t.id)
def test_kademe_secicileri_tuple_olarak_tanimli(tanim) -> None:
    assert isinstance(tanim.tier_selectors, tuple)

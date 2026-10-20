"""Üretim sürerken yanıt okunmaz — "durdur" düğmesi GERÇEKTEN eşleşmelidir.

Ölçüldü (Gemini web, canlı DOM dökümü): üretim sürerken sayfadaki düğmenin
etiketi `aria-label="Yanıtı durdur"` idi. Tanımdaki seçici ise
`button[aria-label*="Durdur"]` — CSS öznitelik eşleşmesi büyük/küçük harfe
DUYARLIDIR, dolayısıyla bu seçici hiçbir zaman eşleşmedi. Sonuç: `generating`
her turda `False` kaldı ve yanıtın bittiğine yalnızca "metin 1,5 sn değişmedi"
ölçütüyle karar verildi.

İki gözlenmiş zarar:

1. Gemini web'de arama yaparken yanıt kutusuna önce "Web'de aranıyor" yazıyor ve
   bu metin saniyelerce durağan kalıyor. Bekleyici onu NİHAİ CEVAP sanıp
   döndürdü; agent turu araç çağrısı olmadan kapandı ve koşu
   "değiştirici araç doğrulanamadı" hatasıyla öldü.
2. Uzun bir cevap üretilirken akış 1,5 sn duraklarsa yarım metin tam sanılır.
   Ölçülen bir kod üretimi turu 12,3 sn sürdü; bu sürenin tamamı boyunca düğme
   görünürdü ama tanımdaki seçici onu göremiyordu.

Bu dosya iki şeyi kilitler: değer içeren `aria-label` seçicileri büyük/küçük
harf duyarsız bayrağı (` i`) taşır ve üretim sürerken durağan metin
döndürülmez.
"""

from __future__ import annotations

import re

import pytest

from fusion_cli.providers import web_browser
from fusion_cli.providers.web_browser import (
    WEB_BROWSER_PROVIDERS,
    WebBrowserSelectorError,
    _wait_for_response,
)

TANIM = WEB_BROWSER_PROVIDERS["gemini_web"]

#: Değer eşleşmesi yapan öznitelik seçicisi: `[aria-label*="…"]`.
DEGERLI_ARIA = re.compile(r'\[aria-label\*="[^"]+"(?P<bayrak>[^\]]*)\]')


def _tum_seciciler() -> list[tuple[str, str]]:
    seciciler: list[tuple[str, str]] = []
    for tanim in WEB_BROWSER_PROVIDERS.values():
        for grup in (tanim.input_selectors, tanim.send_selectors, tanim.stop_selectors):
            seciciler.extend((tanim.id, secici) for secici in grup)
    return seciciler


def test_deger_iceren_aria_seciciler_harf_duyarsizdir() -> None:
    """Arayüz etiketleri yerelleştirilir; "Durdur" ile "durdur" aynı düğmedir."""
    for saglayici, secici in _tum_seciciler():
        eslesme = DEGERLI_ARIA.search(secici)
        if eslesme is None:
            continue
        assert eslesme.group("bayrak").strip() == "i", (
            f"{saglayici} seçicisi büyük/küçük harfe duyarlı: {secici}"
        )


def test_her_saglayicinin_durdur_secicisi_vardir() -> None:
    """Durdur seçicisi olmayan sağlayıcıda tur bitişi ölçülemez, tahmin edilir."""
    for tanim in WEB_BROWSER_PROVIDERS.values():
        assert tanim.stop_selectors, f"{tanim.id} için durdur seçicisi tanımlı değil"


class _SahteLocator:
    def __init__(self, metinler: list[str], *, gorunur: bool = False) -> None:
        self._metinler = metinler
        self._gorunur = gorunur
        self.last = self
        self.first = self

    async def all_inner_texts(self) -> list[str]:
        return self._metinler

    async def count(self) -> int:
        return 1 if self._gorunur else 0

    async def is_visible(self, **_kwargs: object) -> bool:
        return self._gorunur


class _UretimSurenSayfa:
    """Yanıt metni durağan, ama "durdur" düğmesi hâlâ görünür olan sayfa."""

    def __init__(self, metin: str, *, uretim_suruyor: bool) -> None:
        self._metin = metin
        self._uretim_suruyor = uretim_suruyor

    def locator(self, secici: str) -> _SahteLocator:
        if secici in TANIM.stop_selectors:
            return _SahteLocator([], gorunur=self._uretim_suruyor)
        if secici == TANIM.response_selectors[0]:
            return _SahteLocator(["eski", self._metin])
        return _SahteLocator([])


@pytest.fixture(autouse=True)
def _hizli_bekleme(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _sleep(_saniye: float) -> None:
        return None

    monkeypatch.setattr(web_browser.asyncio, "sleep", _sleep)

    async def _hata_yok(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(web_browser, "_raise_known_page_error", _hata_yok)
    monkeypatch.setattr(web_browser, "_raise_if_blocked", _hata_yok)
    monkeypatch.setattr(web_browser.time, "monotonic", _artan_saat(adim=20.0))


def _artan_saat(adim: float = 1.0):
    durum = {"t": 0.0}

    def _monotonic() -> float:
        durum["t"] += adim
        return durum["t"]

    return _monotonic


async def test_uretim_surerken_duragan_metin_dondurulmez() -> None:
    """Asıl regresyon: "Web'de aranıyor" ara metni nihai cevap sanılıyordu."""
    sayfa = _UretimSurenSayfa("Web'de aranıyor", uretim_suruyor=True)

    with pytest.raises(WebBrowserSelectorError, match="yeni bir yanıt üretmedi"):
        await _wait_for_response(sayfa, TANIM, ("eski",))


async def test_uretim_bitince_metin_dondurulur() -> None:
    sayfa = _UretimSurenSayfa("nihai cevap", uretim_suruyor=False)

    sonuc = await _wait_for_response(sayfa, TANIM, ("eski",))

    assert sonuc == "nihai cevap"

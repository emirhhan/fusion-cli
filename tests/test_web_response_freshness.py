"""Bir turun yanıtı, ÖNCEKİ turun yanıtı olamaz.

Ölçüldü (Gemini web, iz kaydı): iki ardışık tur birebir aynı cevabı döndürdü.
Model tekrarlamıyordu — yanıt bekleyici aynı cevabı ikinci kez okuyordu. Agent onu
yeni sanıp aynı araçları tekrar çalıştırdı ve tekrar kapısı turu kesti. Kullanıcının
"döngüye giriyor" dediği davranışın kaynağı buydu.
"""

from __future__ import annotations

import pytest

from fusion_cli.providers import web_browser
from fusion_cli.providers.web_browser import (
    WEB_BROWSER_PROVIDERS,
    WebBrowserSelectorError,
    _wait_for_response,
)

TANIM = WEB_BROWSER_PROVIDERS["gemini_web"]


class _FakeLocator:
    def __init__(self, texts: list[str]) -> None:
        self._texts = texts
        #: Playwright'ta `.last` bir locator döndürür; sahte kendini verir.
        self.last = self

    async def all_inner_texts(self) -> list[str]:
        return self._texts

    async def count(self) -> int:
        return 0

    async def is_visible(self) -> bool:
        return False


class _FakePage:
    """Yanıt listesi ADIM ADIM değişen sahte sayfa."""

    def __init__(self, adimlar: list[list[str]]) -> None:
        self._adimlar = adimlar
        self._index = 0

    def locator(self, selector: str) -> _FakeLocator:
        # Yalnızca ilk seçici eşleşsin: gerçek sayfada da tek yanıt kümesi vardır.
        if selector != TANIM.response_selectors[0]:
            return _FakeLocator([])
        adim = self._adimlar[min(self._index, len(self._adimlar) - 1)]
        self._index += 1
        return _FakeLocator(list(adim))


@pytest.fixture(autouse=True)
def _hizli_bekleme(monkeypatch):
    """Testler gerçek 1.5 sn kararlılık penceresini beklemesin."""
    async def _sleep(_seconds):
        return None

    monkeypatch.setattr(web_browser.asyncio, "sleep", _sleep)

    async def _hata_yok(*args, **kwargs):
        return None

    monkeypatch.setattr(web_browser, "_raise_known_page_error", _hata_yok)


async def test_yeni_yanit_gelince_dondurulur(monkeypatch):
    monkeypatch.setattr(web_browser.time, "monotonic", _artan_saat())
    page = _FakePage([["eski"], ["eski", "yeni"], ["eski", "yeni"], ["eski", "yeni"]])

    sonuc = await _wait_for_response(page, TANIM, ("eski",))

    assert sonuc == "yeni"


async def test_yeni_yanit_yoksa_eski_dondurulmez(monkeypatch):
    """Asıl regresyon: doğrulanamayan yanıt, yanlış yanıttan iyidir."""
    monkeypatch.setattr(web_browser.time, "monotonic", _artan_saat(adim=20.0))
    page = _FakePage([["eski"]])

    with pytest.raises(WebBrowserSelectorError, match="yeni bir yanıt üretmedi"):
        await _wait_for_response(page, TANIM, ("eski",))


async def test_ayni_metinli_yeni_yanit_da_kabul_edilir(monkeypatch):
    """Model aynı metni tekrar üretebilir; ölçüt ÖĞE SAYISIDIR, metin değil."""
    monkeypatch.setattr(web_browser.time, "monotonic", _artan_saat())
    page = _FakePage([["ayni"], ["ayni", "ayni"], ["ayni", "ayni"], ["ayni", "ayni"]])

    sonuc = await _wait_for_response(page, TANIM, ("ayni",))

    assert sonuc == "ayni"


def _artan_saat(adim: float = 1.0):
    """Her çağrıda ilerleyen sahte monoton saat."""
    durum = {"t": 0.0}

    def _monotonic() -> float:
        durum["t"] += adim
        return durum["t"]

    return _monotonic


async def test_onceki_cevapla_ayni_metin_yeni_sayilmaz(monkeypatch):
    """Asıl regresyon: her tur BİR CEVAP GERİDEN yanıtlanıyordu.

    Gerçek koşu izinde prompt çiftleri birebir aynıydı: gönderilen mesaj bir önceki
    turun cevabıyla karşılanıyor, agent onu yeni sanıp aynı araçları tekrar
    çalıştırıyordu. Öğe sayısı büyümüş görünse bile metin öncekiyle aynıysa bu yeni
    bir yanıt değildir.
    """
    monkeypatch.setattr(web_browser.time, "monotonic", _artan_saat(adim=20.0))
    # Sayı artıyor ama metin önceki cevabın aynısı.
    page = _FakePage([["eski"], ["eski", "eski"], ["eski", "eski"]])

    with pytest.raises(WebBrowserSelectorError, match="yeni bir yanıt üretmedi"):
        await _wait_for_response(page, TANIM, ("eski",), previous="eski")


async def test_onceki_cevaptan_farkli_metin_kabul_edilir(monkeypatch):
    monkeypatch.setattr(web_browser.time, "monotonic", _artan_saat())
    page = _FakePage([["eski"], ["eski", "taze"], ["eski", "taze"], ["eski", "taze"]])

    sonuc = await _wait_for_response(page, TANIM, ("eski",), previous="eski")

    assert sonuc == "taze"

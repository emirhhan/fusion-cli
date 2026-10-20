"""Cevap sayfada hazırken tur 180 saniye beklemez.

Ölçüldü (17 Eylül denetimi): web sağlayıcı turlarında model çağrılarının çoğu
9–12 sn sürerken bir kısmı TAM 192 sn sürdü. 192 sn = `_wait_for_response`
sınırının 180 sn'si + `_transport`'un ikinci denemesi. Yani cevap sayfada hazırdı,
bekleyici bitişi göremedi ve doğru cevap ancak tur baştan çalıştırılınca geldi.

Bu dosya yeni kabul yolunu kilitler: yanıt ÖĞE SAYISI artmasa bile metin bu tur
içinde değişip sessizleşirse bekleme ERKEN biter; metin büyümeye devam ederken
bitmez; sayfada bu tura ait hiçbir şey yoksa eski zaman aşımı davranışı korunur.
"""

from __future__ import annotations

import pytest

from fusion_cli.providers import web_browser
from fusion_cli.providers.web_browser import (
    RESPONSE_QUIET_S,
    WEB_BROWSER_PROVIDERS,
    WebBrowserSelectorError,
    _wait_for_response,
)

TANIM = WEB_BROWSER_PROVIDERS["gemini_web"]

#: Tur bütçesi. Gerçek varsayılan 180 sn; test bütçeyi kısaltmaz ki "erken bitti"
#: iddiası ölçülebilsin.
LIMIT_S = 180.0


class _SahteSaat:
    """Yalnızca `sleep` ile ilerleyen monoton saat — testler gerçek süre beklemez."""

    def __init__(self) -> None:
        self.simdi = 0.0

    def monotonic(self) -> float:
        return self.simdi

    async def sleep(self, saniye: float) -> None:
        self.simdi += saniye


class _SahteLocator:
    def __init__(self, metinler: list[str], *, gorunur: bool = False) -> None:
        self._metinler = metinler
        self._gorunur = gorunur
        self.last = self
        self.first = self

    async def all_inner_texts(self) -> list[str]:
        return list(self._metinler)

    async def count(self) -> int:
        return 1 if self._gorunur else 0

    async def is_visible(self, **_kwargs: object) -> bool:
        return self._gorunur


class _TekOgeliSayfa:
    """Yanıtı akıtan, ama eşleşen ÖĞE SAYISI HİÇ ARTMAYAN sahte sayfa.

    Gerçek karşılığı: uzun sohbette sanallaştırma eski turları DOM'dan düşürür ya
    da seçici yedeğe kayar. Cevap gelir, sayı artmaz — eski ölçüt bunu göremiyordu.
    """

    def __init__(self, saat: _SahteSaat, *, buyume_sonu: float, uretim_sonu: float) -> None:
        self._saat = saat
        self._buyume_sonu = buyume_sonu
        self._uretim_sonu = uretim_sonu

    def locator(self, secici: str) -> _SahteLocator:
        if secici in TANIM.stop_selectors:
            return _SahteLocator([], gorunur=self._saat.simdi < self._uretim_sonu)
        if secici == TANIM.response_selectors[0]:
            return _SahteLocator([self._metin()])
        return _SahteLocator([])

    def _metin(self) -> str:
        gecen = min(self._saat.simdi, self._buyume_sonu)
        return "yeni cevap" + "." * int(gecen)


class _BosSayfa:
    """Gönderimden sonra hiçbir şey değişmeyen sayfa: cevap hiç gelmiyor."""

    def locator(self, secici: str) -> _SahteLocator:
        if secici == TANIM.response_selectors[0]:
            return _SahteLocator(["eski"])
        return _SahteLocator([])


@pytest.fixture
def saat(monkeypatch: pytest.MonkeyPatch) -> _SahteSaat:
    """Saat ve uyku tek kaynaktan sürülür; testler gerçek zaman harcamaz."""
    sahte = _SahteSaat()
    monkeypatch.setattr(web_browser.time, "monotonic", sahte.monotonic)
    monkeypatch.setattr(web_browser.asyncio, "sleep", sahte.sleep)

    async def _hata_yok(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(web_browser, "_raise_known_page_error", _hata_yok)
    monkeypatch.setattr(web_browser, "_raise_if_blocked", _hata_yok)
    return sahte


async def test_metin_kararlilasinca_bekleme_erken_biter(saat: _SahteSaat) -> None:
    """Asıl regresyon: öğe sayısı artmasa da sessizleşen metin kabul edilir."""
    sayfa = _TekOgeliSayfa(saat, buyume_sonu=8.0, uretim_sonu=8.0)

    sonuc = await _wait_for_response(sayfa, TANIM, ("eski",), limit_s=LIMIT_S)

    assert sonuc.startswith("yeni cevap")
    # Sessizlik penceresi kadar bekler, tur bütçesi kadar değil.
    assert saat.simdi < 8.0 + RESPONSE_QUIET_S + 2.0
    assert saat.simdi < LIMIT_S


async def test_metin_buyurken_bekleme_surer(saat: _SahteSaat) -> None:
    """Akış sürerken yarım metin kabul edilmez; kabul ancak büyüme bitince gelir."""
    sayfa = _TekOgeliSayfa(saat, buyume_sonu=40.0, uretim_sonu=40.0)

    sonuc = await _wait_for_response(sayfa, TANIM, ("eski",), limit_s=LIMIT_S)

    assert sonuc == "yeni cevap" + "." * 40
    assert saat.simdi >= 40.0 + RESPONSE_QUIET_S


async def test_hic_yanit_gelmezse_zaman_asimi_korunur(saat: _SahteSaat) -> None:
    """Sayfada bu tura ait hiçbir şey yoksa davranış eskisi gibi: hata fırlatılır."""
    with pytest.raises(WebBrowserSelectorError, match="yeni bir yanıt üretmedi"):
        await _wait_for_response(_BosSayfa(), TANIM, ("eski",), limit_s=LIMIT_S)

    assert saat.simdi >= LIMIT_S

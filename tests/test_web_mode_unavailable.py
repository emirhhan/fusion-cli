"""Pasif model/mod seçeneği: tıklanmaz, mevcut kiple sürülür (30 Ekim denemesi).

Ölçüldü (30 Ekim, Gemini web, "3.1 Pro" seçili): menüdeki seçenek
`aria-disabled="true"` idi; `Locator.click` "element is not enabled" diye 5 sn bekleyip
zaman aşımına düştü ve onlarca satırlık Playwright "Call log" ekrana basıldı.
"""

from __future__ import annotations

import logging
import time

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.redaction import strip_driver_log
from fusion_cli.providers import web_browser
from fusion_cli.providers.web_browser import (
    WEB_BROWSER_PROVIDERS,
    BrowserSessionPool,
    WebBrowserModeUnavailableError,
    WebBrowserSelectorError,
    ensure_model_choice,
    switch_to_adjacent_model,
)
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn

from .fakes import request

TANIM = WEB_BROWSER_PROVIDERS["gemini_web"]

CALL_LOG = """Locator.click: Timeout 5000ms exceeded.
Call log:
  - waiting for locator("[role=\\"menu\\"]:visible").last.locator("gem-menu-item").nth(2)
    - locator resolved to <gem-menu-item role="menuitem" aria-disabled="true">…</gem-menu-item>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is not enabled
"""


class _SurucuError(Exception):
    """Playwright `TimeoutError` benzeri: yerleşik `TimeoutError` DEĞİL."""


class _Secenek:
    def __init__(self, etiket: str, *, pasif: bool = False, tiklama_hatasi: str = "") -> None:
        self.etiket = etiket
        self.pasif = pasif
        self.tiklama_hatasi = tiklama_hatasi
        self.tiklandi = 0

    async def inner_text(self) -> str:
        return self.etiket

    async def is_visible(self) -> bool:
        return True

    async def get_attribute(self, ad: str) -> str | None:
        return "true" if ad == "aria-disabled" and self.pasif else None

    async def click(self, **kwargs) -> None:
        self.tiklandi += 1
        if self.pasif or self.tiklama_hatasi:
            raise _SurucuError(self.tiklama_hatasi or CALL_LOG)


class _Liste:
    def __init__(self, ogeler: list[object]) -> None:
        self.ogeler = ogeler

    @property
    def first(self):
        return self.ogeler[0]

    @property
    def last(self):
        return self.ogeler[-1]

    async def count(self) -> int:
        return len(self.ogeler)

    def nth(self, i: int):
        return self.ogeler[i]

    def locator(self, selector: str):
        return _Liste(self.ogeler)

    async def wait_for(self, **kwargs) -> None:
        return None


class _Dugme:
    async def wait_for(self, **kwargs) -> None:
        return None

    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True

    async def click(self, **kwargs) -> None:
        return None

    async def inner_text(self) -> str:
        return "Pro"

    async def get_attribute(self, ad: str) -> str | None:
        return None


class _Klavye:
    def __init__(self) -> None:
        self.tuslar: list[str] = []

    async def press(self, tus: str) -> None:
        self.tuslar.append(tus)


class _Menu:
    def __init__(self, secenekler: list[_Secenek]) -> None:
        self.secenekler = secenekler

    async def wait_for(self, **kwargs) -> None:
        return None

    def locator(self, selector: str):
        return _Liste(self.secenekler)


class _Sayfa:
    def __init__(self, secenekler: list[_Secenek]) -> None:
        self.secenekler = secenekler
        self.keyboard = _Klavye()

    def locator(self, selector: str):
        if "bard-mode-menu-button" in selector:
            return _Liste([_Dugme()])
        return _Liste([_Menu(self.secenekler)])


def _oturum() -> WebSessionConfig:
    return WebSessionConfig(
        model="gemini_web/main/auto",
        provider="gemini_web",
        account="main",
        transport="browser",
        tool_support="emulated",
        selected_model="3.1 Pro",
    )


async def test_pasif_secenege_tiklanmaz_ve_hizlica_ozel_hata_verir():
    pasif = _Secenek("3.1 Pro", pasif=True)
    sayfa = _Sayfa([_Secenek("3.6 Flash"), _Secenek("Flash-Lite"), pasif])

    basla = time.monotonic()
    with pytest.raises(WebBrowserModeUnavailableError, match="pasif"):
        await ensure_model_choice(sayfa, TANIM, "3.1 Pro")

    assert pasif.tiklandi == 0
    assert time.monotonic() - basla < 1.0
    assert sayfa.keyboard.tuslar == ["Escape"]  # menü açık kalmaz


async def test_tiklama_hatasi_ham_gunluksuz_secici_hatasina_cevrilir(caplog):
    secenek = _Secenek("3.1 Pro", tiklama_hatasi=CALL_LOG)
    sayfa = _Sayfa([secenek])

    with caplog.at_level(logging.WARNING), pytest.raises(WebBrowserSelectorError) as hata:
        await ensure_model_choice(sayfa, TANIM, "3.1 Pro")

    assert not isinstance(hata.value, WebBrowserModeUnavailableError)
    assert "Call log" not in str(hata.value)
    assert str(hata.value).count("\n") == 0
    assert "model seçeneği tıklanamadı" in str(hata.value)


async def test_komsu_gecisi_pasif_komsuyu_atlar():
    pasif = _Secenek("Flash-Lite", pasif=True)
    flash = _Secenek("3.6 Flash")
    pro = _Secenek("3.1 Pro")
    sayfa = _Sayfa([flash, pro, pasif])

    secilen = await switch_to_adjacent_model(sayfa, TANIM, "3.1 Pro")

    assert secilen == "3.6 Flash"
    assert flash.tiklandi == 1 and pasif.tiklandi == 0


async def test_apply_model_choice_pasif_modda_bos_secim_doner_ve_bir_kez_not_birakir(
    monkeypatch,
):
    async def _pasif(page, definition, choice):
        raise WebBrowserModeUnavailableError("pasif")

    monkeypatch.setattr(web_browser, "ensure_model_choice", _pasif)
    havuz = BrowserSessionPool()
    oturum = _oturum()

    secim = await web_browser._apply_model_choice(havuz, oturum, TANIM, object())
    ilk_not = havuz.take_mode_note(oturum)
    await web_browser._apply_model_choice(havuz, oturum, TANIM, object())

    assert secim == ""
    assert "3.1 Pro" in ilk_not and "mevcut" in ilk_not
    assert "\n" not in ilk_not
    assert havuz.take_mode_note(oturum) == ""  # aynı süre içinde tekrar yok


async def test_adaptor_web_notunu_yalniz_bagli_alicıya_iletir():
    notlar: list[str] = []

    async def tasima(kimlik, mesajlar, model):
        return WebTurn("cevap", "Flash-Lite", "mod pasif")

    adaptor = WebProviderAdapter(
        model="gemini_web/main/auto", credential=WebSessionCredential(), transport=tasima
    )
    await adaptor.complete(request())  # alıcı yok: sessiz
    adaptor.bind_note_sink(notlar.append)
    sonuc = await adaptor.complete(request())

    assert sonuc.text == "cevap" and sonuc.served_by == "Flash-Lite"
    assert notlar == ["mod pasif"]


async def test_adaptor_ham_surucu_gunlugunu_hata_metnine_koymaz():
    async def tasima(kimlik, mesajlar, model):
        raise _SurucuError(CALL_LOG)

    adaptor = WebProviderAdapter(
        model="gemini_web/main/auto", credential=WebSessionCredential(), transport=tasima
    )

    sonuc = await adaptor.complete(request())

    assert sonuc.ok is False
    assert sonuc.error is not None and sonuc.error.startswith("web oturumu hatası: ")
    assert "Call log" not in sonuc.error and "\n" not in sonuc.error
    assert len(sonuc.error) < 140


def test_strip_driver_log_tek_satir_ve_sinirli():
    ozet = strip_driver_log(CALL_LOG)
    assert ozet == "Locator.click: Timeout 5000ms exceeded"
    assert len(strip_driver_log("x " * 500)) <= 160


async def test_fabrika_web_notunu_durum_satiri_olarak_yayinlar():
    from fusion_cli.core.events import StatusChanged
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.providers.factory import build_provider

    async def tasima(kimlik, mesajlar, model):
        return WebTurn("cevap", "Flash-Lite", "Gemini Web: '3.1 Pro' modu kullanılamıyor")

    class _Kayit:
        def build(self, model, **kwargs):
            return WebProviderAdapter(
                model=model, credential=WebSessionCredential(), transport=tasima
            )

    class _Yayinci:
        def __init__(self) -> None:
            self.olaylar: list[object] = []

        def publish(self, event: object) -> None:
            self.olaylar.append(event)

    yayinci = _Yayinci()
    saglayici = build_provider(
        ModelSpec(name="agent", model="gemini_web/main/auto"),
        publisher=yayinci,
        retry_delays_s=(),
        web_sessions=_Kayit(),
    )

    await saglayici.complete(request())

    durumlar = [o.message for o in yayinci.olaylar if isinstance(o, StatusChanged)]
    assert durumlar == ["Gemini Web: '3.1 Pro' modu kullanılamıyor"]

"""Playwright tarayıcı araçları (T1-36, T1-37, T1-38)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fusion_cli.core.browser_session import BrowserSession
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import browser


class _Sayfa:
    url = "https://x.test/"

    def __init__(self, hatalar: int = 0):
        self.hatalar = hatalar
        self.beklemeler = 0

    async def title(self):
        return "Başlık"

    def locator(self, _s):
        sayfa = self

        class _L:
            async def inner_text(self, **_kwargs):
                if sayfa.hatalar:
                    sayfa.hatalar -= 1
                    raise RuntimeError(
                        "Execution context was destroyed, most likely because of a navigation"
                    )
                return "gövde metni"

        return _L()

    async def wait_for_load_state(self, *_a, **_k):
        self.beklemeler += 1


async def test_ozet_baglam_yok_olunca_bir_kez_yeniden_dener():
    """Tıklama sırasında navigasyon başlarsa "Sayfa okunamadı" dönüp model tekrar tıklıyordu."""
    sayfa = _Sayfa(hatalar=1)

    sonuc = await browser._sayfa_ozeti(sayfa, "tıklandı")

    assert sonuc.ok and "gövde metni" in sonuc.output
    assert sayfa.beklemeler >= 1


async def test_ozet_kalici_hatada_eylemin_yapildigini_soyler():
    sayfa = _Sayfa(hatalar=5)

    sonuc = await browser._sayfa_ozeti(sayfa, "tıklandı (düğme)")

    assert not sonuc.ok
    assert "YAPILDI" in sonuc.output and "tekrar" in sonuc.output.lower()


async def test_okuma_hatasi_eylem_ifadesi_icermez():
    sonuc = await browser._sayfa_ozeti(_Sayfa(hatalar=5), "okundu")

    assert not sonuc.ok and "YAPILDI" not in sonuc.output


async def test_es_zamanli_ilk_cagrilar_tek_tarayici_baslatir(monkeypatch):
    """İki eşzamanlı ilk çağrı iki Chromium başlatıp birini sızdırıyordu."""
    baslatma = {"n": 0}

    class _Context:
        async def new_page(self):
            return object()

    class _Browser:
        async def new_context(self):
            return _Context()

    class _Chromium:
        async def launch(self, headless=True):
            baslatma["n"] += 1
            await asyncio.sleep(0.05)
            return _Browser()

    class _PW:
        chromium = _Chromium()

    class _Surucu:
        async def start(self):
            return _PW()

    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: _Surucu())

    async def _guard(*_a, **_k):
        return None

    monkeypatch.setattr(browser, "install_request_guard", _guard)
    # `ToolContext.root` bir `Path`; #438'den beri oturum başlatma kökün çalışan önizleme
    # kökenlerini de okur (`root.resolve()`), dize kök bu yolda geçersizdir.
    context = ToolContext(root=Path(), browser=BrowserSession())

    sonuclar = await asyncio.gather(browser._sayfa(context), browser._sayfa(context))

    assert baslatma["n"] == 1
    assert all(sayfa is not None for sayfa, _ in sonuclar)


@pytest.mark.parametrize("ham", ["localhost:3000", "127.0.0.1:8080/x", "[::1]:5000"])
def test_semasiz_yerel_adres_http_alir(ham):
    assert browser.normalize_url(ham).startswith("http://")


def test_semasiz_dis_adres_https_alir():
    assert browser.normalize_url("ornek.com/a") == "https://ornek.com/a"
    assert browser.normalize_url("http://ornek.com") == "http://ornek.com"


def test_arac_aciklamasi_yerel_sunucu_gercegini_soyler():
    from fusion_cli.tools import build_registry

    aciklama = build_registry().get("browser_open").description

    assert "localhost engellenir" not in aciklama
    assert "Yerel adres" in aciklama


@pytest.mark.parametrize(
    ("ham", "beklenen"), [("false", False), (False, False), (None, True), ("true", True)]
)
def test_full_page_bool_toleransi(ham, beklenen):
    assert browser._full_page({} if ham is None else {"full_page": ham}) is beklenen

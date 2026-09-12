"""Tur penceresinin gizlenmesi — CDP yolu ve hata dayanıklılığı."""
from __future__ import annotations

import pytest

from fusion_cli.providers.web_browser import _hide_browser_window


class SahteCdp:
    def __init__(self, patlasin: str = "") -> None:
        self.cagrilar: list[tuple[str, dict | None]] = []
        self.ayrildi = False
        self._patlasin = patlasin

    async def send(self, name: str, params: dict | None = None):
        self.cagrilar.append((name, params))
        if self._patlasin == name:
            raise RuntimeError("CDP reddetti")
        if name == "Browser.getWindowForTarget":
            return {"windowId": 7}
        return {}

    async def detach(self) -> None:
        self.ayrildi = True


class SahteContext:
    def __init__(self, cdp: SahteCdp, sayfali: bool = True) -> None:
        self.pages = ["sayfa"] if sayfali else []
        self._cdp = cdp
        self.yeni_sayfa = 0

    async def new_page(self):
        self.yeni_sayfa += 1
        return "sayfa"

    async def new_cdp_session(self, page):
        assert page == "sayfa"
        return self._cdp


@pytest.mark.asyncio
async def test_pencere_cdp_ile_kucultulur():
    cdp = SahteCdp()

    await _hide_browser_window(SahteContext(cdp))

    assert cdp.cagrilar[0][0] == "Browser.getWindowForTarget"
    ad, parametre = cdp.cagrilar[1]
    assert ad == "Browser.setWindowBounds"
    assert parametre == {"windowId": 7, "bounds": {"windowState": "minimized"}}
    assert cdp.ayrildi is True


@pytest.mark.asyncio
async def test_cdp_reddederse_tur_durmaz():
    """Pencereyi küçültememek turun ön koşulu değildir; yalnız kullanıcı görür."""
    cdp = SahteCdp(patlasin="Browser.setWindowBounds")

    await _hide_browser_window(SahteContext(cdp))

    assert cdp.ayrildi is True


@pytest.mark.asyncio
async def test_sayfa_yoksa_acilir():
    cdp = SahteCdp()
    context = SahteContext(cdp, sayfali=False)

    await _hide_browser_window(context)

    assert context.yeni_sayfa == 1

"""Sayfa hatası sınıflandırması — geçici arıza kota sanılmamalı.

Ölçüldü: Gemini geçici arızada "Something went wrong, try again later" gösteriyor.
Bu ifade kota işaretleri arasındaydı ve Fusion kullanıcıya "kullanım/kota sınırı"
diyordu. Kullanıcı bunun üzerine yeni bir hesap açtı — oysa sorun kota değildi.
Yanlış teşhis, teşhis yokluğundan zararlıdır.

Ayrıca tarama sayfanın TAMAMINI kapsıyordu; modelin kendi cevabı da dahil. Model
"rate limit" yazdığı anda Fusion bunu sağlayıcının uyarısı sanardı.
"""

from __future__ import annotations

import pytest

from fusion_cli.providers.web_browser import (
    WEB_BROWSER_PROVIDERS,
    WebBrowserError,
    _raise_known_page_error,
)

TANIM = WEB_BROWSER_PROVIDERS["gemini_web"]


class _Locator:
    def __init__(self, texts: list[str]) -> None:
        self._texts = texts
        self.last = self

    # Playwright imzası; sahte olduğu için gerçek zaman aşımı uygulamaz.
    async def inner_text(self, timeout: int = 0) -> str:  # noqa: ASYNC109
        return self._texts[0] if self._texts else ""

    async def all_inner_texts(self) -> list[str]:
        return list(self._texts)

    async def count(self) -> int:
        return 0

    async def is_visible(self) -> bool:
        return False


class _Page:
    """Gövde metni ve model cevabı ayrı ayrı verilebilen sahte sayfa."""

    def __init__(self, body: str, answers: list[str] | None = None) -> None:
        self._body = body
        self._answers = answers or []
        self.url = "https://gemini.google.com/app"

    def locator(self, selector: str) -> _Locator:
        if selector == "body":
            return _Locator([self._body])
        if selector == TANIM.response_selectors[0]:
            return _Locator(self._answers)
        return _Locator([])


async def test_gecici_hata_kota_olarak_bildirilmez():
    page = _Page("Something went wrong. Try again later.")

    with pytest.raises(WebBrowserError) as hata:
        await _raise_known_page_error(page, TANIM)

    assert "kota DEĞİL" in str(hata.value)
    assert "kullanım/kota sınırı" not in str(hata.value)


async def test_gercek_kota_uyarisi_kota_olarak_bildirilir():
    page = _Page("You've reached your limit for this model.")

    with pytest.raises(WebBrowserError, match="kullanım/kota sınırı"):
        await _raise_known_page_error(page, TANIM)


async def test_modelin_kendi_metni_saglayici_uyarisi_sayilmaz():
    """Model 'rate limit' yazınca Fusion kotan doldu demezdi."""
    cevap = "API'lerde rate limit aşılırsa 429 döner; too many requests hatası alırsın."
    page = _Page(f"Gemini\n{cevap}\n", answers=[cevap])

    await _raise_known_page_error(page, TANIM)  # hata fırlatmamalı


async def test_temiz_sayfa_hata_uretmez():
    page = _Page("Gemini\nMerhaba, nasıl yardımcı olabilirim?")

    await _raise_known_page_error(page, TANIM)

"""Seçici sırası bir ÖNCELİKTİR; ilk hazır olan değil, en iyisi seçilmeli.

Ölçüldü (11 Eylül, chatgpt_web, gerçek oturum): tur mesaj kutusu olarak
`TEXTAREA.wcDTda_fallbackTextarea` seçiyordu — ChatGPT'nin GİZLİ yedek
textarea'sı. Sayfa yüklenirken o eleman, gerçek ProseMirror kutusundan
(`#prompt-textarea`) önce hazır oluyor ve `_first_visible` ilk eşleşeni hemen
kabul ettiği için liste sırası anlamını yitiriyordu.

Sonuç: prompt gizli kutuya yazılıyor, geri okuma 0 karakter veriyor ve tur
"1483 karakter yazıldı, 0 karakter yerleşti" ile düşüyordu. Yani yarışı kaybeden
tur, arayüz değişmiş gibi görünen bir hatayla ölüyordu.
"""

from __future__ import annotations

from fusion_cli.providers.web_browser import _first_visible


class _Locator:
    def __init__(self, ad: str, *, var: bool, gorunur: bool = True) -> None:
        self.ad = ad
        self._var = var
        self._gorunur = gorunur

    @property
    def last(self) -> _Locator:
        return self

    async def count(self) -> int:
        return 1 if self._var else 0

    async def is_visible(self) -> bool:
        return self._gorunur


class _Page:
    """Gerçek kutu GECİKMELİ gelir; yedek kutu en baştan hazırdır."""

    def __init__(self, gecikme: int) -> None:
        self.tur = 0
        self._gecikme = gecikme

    def locator(self, selector: str) -> _Locator:
        if selector == "#prompt-textarea":
            return _Locator(selector, var=self.tur >= self._gecikme)
        self.tur += 1
        return _Locator(selector, var=True)


async def test_gec_gelen_oncelikli_secici_beklenir():
    page = _Page(gecikme=3)

    loc = await _first_visible(page, ("#prompt-textarea", "textarea"), timeout_ms=8_000)

    assert loc is not None
    assert loc.ad == "#prompt-textarea", "yedek kutu seçildi; öncelik sırası çalışmadı"


async def test_oncelikli_secici_hic_gelmezse_yedek_kullanilir():
    """Öncelikli seçici yoksa tur bloke edilmez; eldekiyle sürdürülür."""
    page = _Page(gecikme=10_000)

    loc = await _first_visible(page, ("#prompt-textarea", "textarea"), timeout_ms=3_000)

    assert loc is not None
    assert loc.ad == "textarea"


async def test_oncelikli_secici_hazirsa_hemen_doner():
    page = _Page(gecikme=0)

    loc = await _first_visible(page, ("#prompt-textarea", "textarea"), timeout_ms=8_000)

    assert loc is not None and loc.ad == "#prompt-textarea"

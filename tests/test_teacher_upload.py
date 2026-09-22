"""Taşan prompt için dosya yükleme (Faz 4, Görev 2) — sahte sayfa, ağ gerektirmez.

Gerçek yükleme akışı 22 Eylül'de canlı bir Gemini web oturumunda doğrulandı
(105.032 karakterlik gerçek dosya, model içeriği birebir okudu). Bu dosya o
akışın KARAR MANTIĞINI (yükle-ya-da-kırp, arıza durumunda kırpmaya geri dönüş)
sahte bir sayfayla kilitler.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from fusion_cli.providers.web_browser import (
    _UPLOAD_NOTICE,
    MAX_WEB_PROMPT_CHARS,
    WEB_BROWSER_PROVIDERS,
    _prepare_prompt_for_composer,
    trim_to_prompt_budget,
)

_GEMINI = WEB_BROWSER_PROVIDERS["gemini_web"]
_CHATGPT = WEB_BROWSER_PROVIDERS["chatgpt_web"]


class _SahtePage:
    """Dokunulursa hata fırlatan sayfa — bütçe altındaki prompt için sayfa HİÇ
    kullanılmamalı, bunu zorlar."""

    async def query_selector_all(self, selector):
        raise AssertionError(f"sayfa dokunulmamalı ama query_selector_all({selector!r}) çağrıldı")


async def test_butce_altindaki_prompt_sayfaya_hic_dokunmadan_doner():
    prompt = "kısa görev"

    sonuc = await _prepare_prompt_for_composer(_SahtePage(), _GEMINI, prompt)

    assert sonuc == prompt


async def test_chatgpt_icin_yukleme_denenmez_dogrudan_kirpilir():
    """ChatGPT headless'ta Cloudflare'a takılıyor (ölçüldü) — yükleme hiç denenmez."""
    prompt = "x" * (MAX_WEB_PROMPT_CHARS + 5_000)

    sonuc = await _prepare_prompt_for_composer(_SahtePage(), _CHATGPT, prompt)

    assert sonuc == trim_to_prompt_budget(prompt)


async def test_gemini_de_tetikleyici_bulunamazsa_kirpmaya_duser(monkeypatch):
    import fusion_cli.providers.web_browser as browser

    monkeypatch.setattr(browser, "_first_visible", AsyncMock(return_value=None))
    prompt = "y" * (MAX_WEB_PROMPT_CHARS + 5_000)

    sonuc = await _prepare_prompt_for_composer(_SahteYukleyiciSayfa(), _GEMINI, prompt)

    assert sonuc == trim_to_prompt_budget(prompt)


class _SahteYukleyiciSayfa:
    """`query_selector_all` çağrılabilir ama gerçek Playwright API'sini taklit etmez;
    yalnız `_first_visible` None döndüğünde erişilmemesi gerektiğini doğrular."""

    async def query_selector_all(self, selector):
        raise AssertionError("tetikleyici bulunamadıysa input aranmamalı")


class _TiklanabilirEleman:
    def __init__(self, *, tiklaninca_hata: bool = False):
        self.tiklandi = False
        self._hata = tiklaninca_hata

    async def click(self):
        if self._hata:
            raise RuntimeError("tıklama başarısız")
        self.tiklandi = True


class _SahteDosyaGirisi:
    def __init__(self):
        self.yuklenen_yollar: list[str] = []

    async def set_input_files(self, path):
        self.yuklenen_yollar.append(path)
        self.icerik = Path(path).read_text(encoding="utf-8")  # noqa: ASYNC240 - test yardımcısı


class _TamAkisSayfasi:
    def __init__(self, *, dosya_girisleri):
        self._dosya_girisleri = dosya_girisleri
        self.wait_calls = 0

    async def query_selector_all(self, selector):
        assert selector == "input[type=file]"
        return self._dosya_girisleri

    async def wait_for_timeout(self, ms):
        self.wait_calls += 1


async def test_gemini_de_secenek_bulunamazsa_kirpmaya_duser(monkeypatch):
    import fusion_cli.providers.web_browser as browser

    tetikleyici = _TiklanabilirEleman()
    mock_first_visible = AsyncMock(side_effect=[tetikleyici, None])
    monkeypatch.setattr(browser, "_first_visible", mock_first_visible)
    prompt = "z" * (MAX_WEB_PROMPT_CHARS + 1_000)

    sonuc = await _prepare_prompt_for_composer(_TamAkisSayfasi(dosya_girisleri=[]), _GEMINI, prompt)

    assert sonuc == trim_to_prompt_budget(prompt)
    assert tetikleyici.tiklandi is True


async def test_gemini_de_input_yoksa_kirpmaya_duser(monkeypatch):
    import fusion_cli.providers.web_browser as browser

    tetikleyici = _TiklanabilirEleman()
    secenek = _TiklanabilirEleman()
    monkeypatch.setattr(
        browser, "_first_visible", AsyncMock(side_effect=[tetikleyici, secenek])
    )
    prompt = "a" * (MAX_WEB_PROMPT_CHARS + 1_000)

    sonuc = await _prepare_prompt_for_composer(_TamAkisSayfasi(dosya_girisleri=[]), _GEMINI, prompt)

    assert sonuc == trim_to_prompt_budget(prompt)
    assert secenek.tiklandi is True


async def test_gemini_de_basarili_yukleme_bildirimi_doner_ve_icerik_dosyaya_yazilir(
    monkeypatch,
):
    import fusion_cli.providers.web_browser as browser

    tetikleyici = _TiklanabilirEleman()
    secenek = _TiklanabilirEleman()
    monkeypatch.setattr(
        browser, "_first_visible", AsyncMock(side_effect=[tetikleyici, secenek])
    )
    eski_giris = _SahteDosyaGirisi()
    yeni_giris = _SahteDosyaGirisi()
    sayfa = _TamAkisSayfasi(dosya_girisleri=[eski_giris, yeni_giris])
    prompt = "GERÇEKÇİ_İÇERİK " * 3_000
    assert len(prompt) > MAX_WEB_PROMPT_CHARS

    sonuc = await _prepare_prompt_for_composer(sayfa, _GEMINI, prompt)

    assert sonuc == _UPLOAD_NOTICE.format(chars=len(prompt))
    # SON eklenen giriş kullanılmalı (ölçüldü: önceki girişler eski/gizli olabilir).
    assert eski_giris.yuklenen_yollar == []
    assert yeni_giris.yuklenen_yollar
    assert yeni_giris.icerik == prompt
    assert sayfa.wait_calls == 1


async def test_yukleme_sirasinda_istisna_sessizce_kirpmaya_duser(monkeypatch):
    """Yükleme İSTEĞE BAĞLI bir iyileştirmedir — hiçbir arıza turu DÜŞÜRMEMELİ."""
    import fusion_cli.providers.web_browser as browser

    tetikleyici = _TiklanabilirEleman(tiklaninca_hata=True)
    monkeypatch.setattr(browser, "_first_visible", AsyncMock(return_value=tetikleyici))
    prompt = "b" * (MAX_WEB_PROMPT_CHARS + 1_000)

    sonuc = await _prepare_prompt_for_composer(_TamAkisSayfasi(dosya_girisleri=[]), _GEMINI, prompt)

    assert sonuc == trim_to_prompt_budget(prompt)

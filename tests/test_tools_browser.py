"""Etkileşimli tarayıcı araçları — gerçek tarayıcı AÇMADAN.

Playwright sınırı sahtelenir: burada sınanan şey Chromium değil, aracın kendi
mantığıdır — oturum taşıyıcısı, SSRF kapısı, "önce aç" kuralı, hata metinleri ve
kapatma yolu. Gerçek tarayıcıyla çalıştığı ayrıca elle doğrulandı (bkz. commit).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.browser_session import BrowserSession
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import browser


class _SahteSayfa:
    """Playwright `Page` yüzeyinin sınanan kadarı."""

    def __init__(self, *, url: str = "about:blank", govde: str = "sayfa içeriği") -> None:
        self.url = url
        self._govde = govde
        self.gidilen: list[str] = []
        self.yazilan: list[tuple[str, str]] = []
        self.tiklanan: list[str] = []
        self.basilan: list[str] = []
        self.goruntu_yollari: list[str] = []
        self.hedef_bulunur = True

    async def goto(self, url: str, **_: object) -> None:
        self.gidilen.append(url)
        self.url = url

    async def title(self) -> str:
        return "Sahte Başlık"

    async def wait_for_load_state(self, *_: object, **__: object) -> None:
        return None

    async def screenshot(self, *, path: str, full_page: bool) -> None:
        del full_page
        self.goruntu_yollari.append(path)
        # Sahte tarayıcı, gerçek playwright gibi diske yazar. Bloklayan yazma burada
        # zararsızdır (birkaç bayt, tmp_path) ve testin ölçtüğü şey değildir.
        Path(path).write_bytes(b"PNG")  # noqa: ASYNC240

    def locator(self, selector: str) -> _SahteLocator:
        return _SahteLocator(self, selector)

    async def close(self) -> None:
        return None


class _SahteLocator:
    def __init__(self, page: _SahteSayfa, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self) -> _SahteLocator:
        return self

    async def wait_for(self, **_: object) -> None:
        if not self._page.hedef_bulunur:
            raise TimeoutError(f"{self._selector} bulunamadı")

    async def fill(self, text: str) -> None:
        self._page.yazilan.append((self._selector, text))

    async def press(self, key: str) -> None:
        self._page.basilan.append(key)

    async def click(self, **_: object) -> None:
        self._page.tiklanan.append(self._selector)

    async def inner_text(self, **_: object) -> str:
        return self._page._govde


def _acik_context(tmp_path: Path, page: _SahteSayfa) -> ToolContext:
    """Oturumu ZATEN açık bir bağlam: playwright hiç başlatılmaz."""
    oturum = BrowserSession()
    oturum.page = page
    return ToolContext(root=tmp_path, browser=oturum)


# --------------------------------------------------------------------------- #
# Oturum taşıyıcısı
# --------------------------------------------------------------------------- #


def test_yeni_oturum_kapalidir():
    assert BrowserSession().is_open is False


async def test_kapatma_tum_kaynaklari_birakir(tmp_path):
    oturum = BrowserSession()
    oturum.page = _SahteSayfa()
    await oturum.close()
    assert oturum.is_open is False
    assert oturum.browser is None and oturum.playwright is None


async def test_kapatma_bir_adim_patlasa_bile_devam_eder():
    """Yarım temizlik, hiç temizlik yapmamaktan iyidir: süreç arkada kalmamalı."""

    class _PatlayanSayfa:
        async def close(self) -> None:
            raise RuntimeError("sayfa zaten kapalı")

    class _Sayan:
        def __init__(self) -> None:
            self.kapandi = False

        async def close(self) -> None:
            self.kapandi = True

        async def stop(self) -> None:
            self.kapandi = True

    tarayici = _Sayan()
    oturum = BrowserSession()
    oturum.page = _PatlayanSayfa()
    oturum.browser = tarayici

    await oturum.close()

    assert tarayici.kapandi, "sayfa hatası tarayıcının kapatılmasını engelledi"
    assert oturum.is_open is False


# --------------------------------------------------------------------------- #
# Açma ve SSRF kapısı
# --------------------------------------------------------------------------- #


async def test_acma_sayfayi_yukler_ve_ozet_doner(tmp_path, monkeypatch):
    # SSRF kapısı DNS çözer; testler ağa çıkmaz. Kapının KENDİSİ ayrıca sınanıyor.
    monkeypatch.setattr(browser, "url_block_reason", lambda url: None)
    page = _SahteSayfa(govde="Spor Ayakkabı 1.499 TL")
    context = _acik_context(tmp_path, page)

    sonuc = await browser.browser_open({"url": "https://ornek.test/urunler"}, context)

    assert sonuc.ok
    assert page.gidilen == ["https://ornek.test/urunler"]
    assert "Spor Ayakkabı" in sonuc.output
    assert "Sahte Başlık" in sonuc.output


async def test_semasiz_adres_https_yapilir(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "url_block_reason", lambda url: None)
    page = _SahteSayfa()
    context = _acik_context(tmp_path, page)

    await browser.browser_open({"url": "ornek.test"}, context)

    assert page.gidilen == ["https://ornek.test"]


async def test_ssrf_kapisi_tarayicida_da_uygulanir(tmp_path):
    """Tarayıcı olması adresi güvenli yapmaz; yerel ağa erişim için daha güçlüdür."""
    page = _SahteSayfa()
    context = _acik_context(tmp_path, page)

    sonuc = await browser.browser_open({"url": "http://127.0.0.1:8080/admin"}, context)

    assert not sonuc.ok
    assert page.gidilen == [], "engellenen adrese yine de gidildi"


async def test_erisim_duvari_tarayicida_da_bildirilir(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "url_block_reason", lambda url: None)
    page = _SahteSayfa(govde="This store is password protected. Enter store password")
    context = _acik_context(tmp_path, page)

    sonuc = await browser.browser_open({"url": "https://magaza.test"}, context)

    assert "ERİŞİM DUVARI" in sonuc.output
    assert "browser_type" in sonuc.output, "modele kapıyı nasıl geçeceği söylenmeli"


# --------------------------------------------------------------------------- #
# Yazma, tıklama ve "önce aç" kuralı
# --------------------------------------------------------------------------- #


async def test_sifre_yazip_gonderme_zinciri(tmp_path):
    page = _SahteSayfa(url="https://magaza.test/password")
    context = _acik_context(tmp_path, page)

    sonuc = await browser.browser_type(
        {"selector": "input[type=password]", "text": "4", "submit": True}, context
    )

    assert sonuc.ok
    assert page.yazilan == [("input[type=password]", "4")]
    assert page.basilan == ["Enter"]


async def test_submit_verilmezse_enter_basilmaz(tmp_path):
    page = _SahteSayfa(url="https://magaza.test/ara")
    context = _acik_context(tmp_path, page)

    await browser.browser_type({"selector": "#q", "text": "ayakkabı"}, context)

    assert page.basilan == []


async def test_tiklama_secilen_ogeye_gider(tmp_path):
    page = _SahteSayfa(url="https://magaza.test")
    context = _acik_context(tmp_path, page)

    sonuc = await browser.browser_click({"selector": "button[type=submit]"}, context)

    assert sonuc.ok
    assert page.tiklanan == ["button[type=submit]"]


async def test_sayfa_acilmadan_yazilamaz(tmp_path):
    context = _acik_context(tmp_path, _SahteSayfa(url="about:blank"))

    sonuc = await browser.browser_type({"selector": "#q", "text": "x"}, context)

    assert not sonuc.ok
    assert "browser_open" in sonuc.output


async def test_bulunamayan_secici_modele_dogrulama_yolunu_soyler(tmp_path):
    page = _SahteSayfa(url="https://magaza.test")
    page.hedef_bulunur = False
    context = _acik_context(tmp_path, page)

    sonuc = await browser.browser_click({"selector": ".olmayan"}, context)

    assert not sonuc.ok
    assert "browser_read" in sonuc.output
    assert "uydurma" in sonuc.output


# --------------------------------------------------------------------------- #
# Okuma, görüntü ve kapatma
# --------------------------------------------------------------------------- #


async def test_okuma_acik_sayfa_yoksa_reddeder(tmp_path):
    sonuc = await browser.browser_read({}, ToolContext(root=tmp_path))

    assert not sonuc.ok
    assert "browser_open" in sonuc.output


async def test_ekran_goruntusu_diske_yazilir_ve_degisiklige_kaydedilir(tmp_path):
    page = _SahteSayfa(url="https://magaza.test")
    context = _acik_context(tmp_path, page)

    sonuc = await browser.browser_screenshot({"path": "site.png"}, context)

    assert sonuc.ok
    assert (tmp_path / "site.png").exists()
    assert (tmp_path / "site.png") in context.touched
    assert context.changes.paths, "/undo görüntüyü görmeli"


async def test_kapali_tarayiciyi_kapatmak_hata_degildir(tmp_path):
    sonuc = await browser.browser_close({}, ToolContext(root=tmp_path))
    assert sonuc.ok


async def test_kapatma_oturumu_gercekten_bosaltir(tmp_path):
    context = _acik_context(tmp_path, _SahteSayfa())

    await browser.browser_close({}, context)

    assert context.browser.is_open is False


# --------------------------------------------------------------------------- #
# Playwright kurulu değilken
# --------------------------------------------------------------------------- #


async def test_playwright_yoksa_kurulum_talimati_doner(tmp_path, monkeypatch):
    """Opsiyonel bağımlılık: uygulama çökmez, anlaşılır talimat döner."""
    import builtins

    gercek_import = builtins.__import__

    def _engelle(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("playwright yok")
        return gercek_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _engelle)
    monkeypatch.setattr(browser, "url_block_reason", lambda url: None)

    sonuc = await browser.browser_open({"url": "https://ornek.test"}, ToolContext(root=tmp_path))

    assert not sonuc.ok
    assert "playwright install chromium" in sonuc.output


# --------------------------------------------------------------------------- #
# Kayıt defteri ve güvenlik duruşu
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("ad", "degistirici"),
    [
        ("browser_open", False),
        ("browser_read", False),
        ("browser_close", False),
        ("browser_type", True),
        ("browser_click", True),
        ("browser_screenshot", True),
    ],
)
def test_araclar_dogru_degistirici_bayragiyla_kayitli(ad, degistirici):
    """Tıklama ve yazma gerçek dünyada geri alınamaz etki yaratır: onaya girmeli."""
    from fusion_cli.tools import build_registry

    tool = build_registry().get(ad)

    assert tool is not None, f"{ad} kayıtlı değil"
    assert tool.mutating is degistirici

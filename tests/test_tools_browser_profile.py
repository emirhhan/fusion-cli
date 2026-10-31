"""`browser_open` profil yükleme (P-023): çerezler `storage_state` ile bağlama girer,
kapanışta geri yazılır.

Playwright sahtelenir (`sys.modules`); gerçek tarayıcı açılmaz. Ölçüldü (31 Ekim): eski
`_oturumu_baslat` her zaman `launch(headless=True)` + boş `new_context()` çağırıyordu.
"""

from __future__ import annotations

import sys
import types

import pytest

from fusion_cli.config.browser_profiles import BrowserProfileStore
from fusion_cli.core.browser_session import BrowserSession
from fusion_cli.core.cookie_files import Cookie
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import browser

GIZLI = "cerez-degeri-GIZLI-77"


class _SahteSayfa:
    url = "about:blank"

    async def goto(self, url: str, **_: object) -> None:
        self.url = url

    async def title(self) -> str:
        return "Başlık"

    def locator(self, _selector: str) -> _SahteSayfa:
        return self

    async def inner_text(self, **_: object) -> str:
        return "gövde"

    def is_closed(self) -> bool:
        return False

    async def close(self) -> None:
        return None


class _SahteBaglam:
    def __init__(self, storage_state: object) -> None:
        self.storage_state_in = storage_state
        self.pages: list[_SahteSayfa] = []
        self.cerez_guncellendi = False

    async def new_page(self) -> _SahteSayfa:
        page = _SahteSayfa()
        self.pages.append(page)
        return page

    async def storage_state(self) -> dict[str, object]:
        # Profilsiz (boş) bağlam boş oturum döndürür; profilli bağlam tazelenmiş çerez.
        if self.storage_state_in is None:
            return {"cookies": [], "origins": []}
        return {
            "cookies": [
                {
                    "name": "sid",
                    "value": "TAZE",
                    "domain": ".example.com",
                    "path": "/",
                    "expires": -1,
                }
            ],
            "origins": [],
        }

    async def close(self) -> None:
        return None


class _SahteTarayici:
    def __init__(self) -> None:
        self.headless: bool | None = None
        self.contexts: list[_SahteBaglam] = []

    async def new_context(self, storage_state: object = None) -> _SahteBaglam:
        context = _SahteBaglam(storage_state)
        self.contexts.append(context)
        return context

    async def close(self) -> None:
        return None


class _SahtePlaywright:
    def __init__(self, tarayici: _SahteTarayici) -> None:
        self._tarayici = tarayici
        self.chromium = self

    async def launch(self, headless: bool = True) -> _SahteTarayici:
        self._tarayici.headless = headless
        return self._tarayici

    async def start(self) -> _SahtePlaywright:
        return self

    async def stop(self) -> None:
        return None


@pytest.fixture
def sahte_playwright(monkeypatch):
    tarayici = _SahteTarayici()
    modul = types.ModuleType("playwright.async_api")
    modul.async_playwright = lambda: _SahtePlaywright(tarayici)  # type: ignore[attr-defined]
    paket = types.ModuleType("playwright")
    monkeypatch.setitem(sys.modules, "playwright", paket)
    monkeypatch.setitem(sys.modules, "playwright.async_api", modul)

    async def _guard(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(browser, "install_request_guard", _guard)
    monkeypatch.setattr(browser, "browser_block_reason", lambda url, allowed=(): None)
    return tarayici


@pytest.fixture
def depo(tmp_path, monkeypatch):
    store = BrowserProfileStore(tmp_path / "bp", secret_key="anahtar", clock=lambda: 1.0)
    store.save(
        "is",
        (
            Cookie(name="sid", value=GIZLI, domain=".example.com"),
            Cookie(name="x", value="y", domain="other.net"),
        ),
        source="dosya",
        allowed_domains=("example.com",),
    )
    monkeypatch.setattr(browser, "default_browser_profile_store", lambda: store)
    return store


async def test_profil_argumani_cerezleri_baglama_yukler_ve_sonucta_adi_yazar(
    tmp_path, sahte_playwright, depo
):
    baglam = ToolContext(root=tmp_path)

    sonuc = await browser.browser_open({"url": "https://example.com", "profile": "is"}, baglam)

    assert sonuc.ok, sonuc.output
    assert sonuc.output.startswith("profil: is\n")
    assert GIZLI not in sonuc.output
    yuklenen = sahte_playwright.contexts[0].storage_state_in
    assert [cookie["name"] for cookie in yuklenen["cookies"]] == ["sid"], "onay dışı alan adı sızdı"
    assert yuklenen["cookies"][0]["value"] == GIZLI
    assert sahte_playwright.headless is True
    assert baglam.browser.active_profile == "is"


async def test_profilsiz_acilis_eski_davranisi_korur(tmp_path, sahte_playwright, depo):
    sonuc = await browser.browser_open({"url": "https://example.com"}, ToolContext(root=tmp_path))

    assert sonuc.ok
    assert not sonuc.output.startswith("profil:")
    assert sahte_playwright.contexts[0].storage_state_in is None


async def test_yapilandirma_varsayilan_profili_ve_headed_kipi_uygular(
    tmp_path, sahte_playwright, depo
):
    baglam = ToolContext(root=tmp_path, browser=BrowserSession(profile_name="is", headless=False))

    sonuc = await browser.browser_open({"url": "https://example.com"}, baglam)

    assert sonuc.ok
    assert sahte_playwright.headless is False
    assert sahte_playwright.contexts[0].storage_state_in is not None


async def test_headed_argumani_pencereyi_gorunur_acar(tmp_path, sahte_playwright, depo):
    await browser.browser_open(
        {"url": "https://example.com", "headed": True}, ToolContext(root=tmp_path)
    )

    assert sahte_playwright.headless is False


async def test_kapanista_tazelenen_cerezler_profile_geri_yazilir(tmp_path, sahte_playwright, depo):
    baglam = ToolContext(root=tmp_path)
    await browser.browser_open({"url": "https://example.com", "profile": "is"}, baglam)

    await browser.browser_close({}, baglam)

    durum = depo.storage_state("is")
    assert durum["cookies"][0]["value"] == "TAZE"
    assert depo.summary("is").allowed_domains == ("example.com",)


async def test_olmayan_profil_tarayici_acmadan_hata_verir(tmp_path, sahte_playwright, depo):
    sonuc = await browser.browser_open(
        {"url": "https://example.com", "profile": "yok"}, ToolContext(root=tmp_path)
    )

    assert not sonuc.ok
    assert "yok" in sonuc.output
    assert sahte_playwright.contexts == []


async def test_profiller_kapaliyken_acik_istek_reddedilir(tmp_path, sahte_playwright, depo):
    baglam = ToolContext(root=tmp_path, browser=BrowserSession(profiles_enabled=False))

    sonuc = await browser.browser_open({"url": "https://example.com", "profile": "is"}, baglam)

    assert not sonuc.ok
    assert "profiles_enabled" in sonuc.output
    assert sahte_playwright.contexts == []


async def test_acik_oturumda_baska_profil_istenirse_once_kapatmayi_soyler(
    tmp_path, sahte_playwright, depo
):
    baglam = ToolContext(root=tmp_path)
    await browser.browser_open({"url": "https://example.com"}, baglam)

    sonuc = await browser.browser_open({"url": "https://example.com", "profile": "is"}, baglam)

    assert not sonuc.ok
    assert "browser_close" in sonuc.output
    assert len(sahte_playwright.contexts) == 1


async def test_kapat_sonra_profilsiz_acilis_onceki_profili_ezmez(tmp_path, sahte_playwright, depo):
    """Ölçüldü (31 Ekim): `state_saver` kapanışta sıfırlanmıyordu; sonraki anonim bağlamın
    boş oturumu önceki profilin çerezlerini siliyordu."""
    baglam = ToolContext(root=tmp_path)
    await browser.browser_open({"url": "https://example.com", "profile": "is"}, baglam)
    await browser.browser_close({}, baglam)
    await browser.browser_open({"url": "https://example.com"}, baglam)

    assert baglam.browser.state_saver is None
    await browser.browser_close({}, baglam)

    durum = depo.storage_state("is")
    assert [cookie["name"] for cookie in durum["cookies"]] == ["sid"]
    assert durum["cookies"][0]["value"] == "TAZE"

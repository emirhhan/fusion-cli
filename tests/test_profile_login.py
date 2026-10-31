"""Görünür pencerede profile giriş (`open_profile_login`, `fusion browser login`) — P-023.

Playwright sahtelenir; gerçek pencere açılmaz. Ölçüldü (31 Ekim): bu akışın hiç testi
yoktu ve tarayıcı bağlantısı koparsa (Cmd+Q) oturum hiç yazılmadan hata veriliyordu.
"""

from __future__ import annotations

import sys
import types

import pytest
from typer.testing import CliRunner

from fusion_cli.config.browser_profiles import BrowserProfileStore
from fusion_cli.core.cookie_files import Cookie
from fusion_cli.core.errors import BrowserProfileError
from fusion_cli.providers import profile_login

GIZLI = "cerez-degeri-GIZLI-44"


class _Sayfa:
    async def goto(self, url: str) -> None:
        self.url = url


class _Baglam:
    """`senaryo`: her yoklamada çalışır; sayfaları boşaltır ya da bağlantıyı keser."""

    def __init__(self, tarayici: _Tarayici, storage_state: object) -> None:
        self.tarayici = tarayici
        self.storage_state_in = storage_state
        self.pages: list[_Sayfa] = []
        self.okuma = 0

    async def new_page(self) -> _Sayfa:
        page = _Sayfa()
        self.pages.append(page)
        return page

    async def storage_state(self) -> dict[str, object]:
        self.okuma += 1
        if not self.tarayici.connected:
            raise RuntimeError("Target closed")
        return {
            "cookies": [
                {"name": "sid", "value": f"{GIZLI}-{self.okuma}", "domain": ".example.com"}
            ],
            "origins": [
                {
                    "origin": "https://app.example.com",
                    "localStorage": [{"name": "jwt", "value": "J"}],
                }
            ],
        }


class _Tarayici:
    def __init__(self) -> None:
        self.connected = True
        self.closed = False
        self.context: _Baglam | None = None

    async def new_context(self, storage_state: object = None) -> _Baglam:
        self.context = _Baglam(self, storage_state)
        return self.context

    def is_connected(self) -> bool:
        return self.connected

    async def close(self) -> None:
        self.closed = True


class _Playwright:
    def __init__(self, tarayici: _Tarayici) -> None:
        self.chromium = self
        self._tarayici = tarayici
        self.headless: bool | None = None

    async def launch(self, headless: bool = True) -> _Tarayici:
        self.headless = headless
        return self._tarayici

    async def __aenter__(self) -> _Playwright:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.fixture
def sahte(monkeypatch):
    tarayici = _Tarayici()
    pw = _Playwright(tarayici)
    modul = types.ModuleType("playwright.async_api")
    modul.async_playwright = lambda: pw  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", modul)
    monkeypatch.setattr(profile_login, "_POLL_INTERVAL_S", 0.0)
    return tarayici, pw


@pytest.fixture
def depo(tmp_path):
    return BrowserProfileStore(tmp_path / "bp", secret_key="anahtar", clock=lambda: 5.0)


def _kullanici(tarayici: _Tarayici, *, kopar: bool, sonra: int = 3):
    """`sonra` yoklamadan sonra kullanıcı pencereyi kapatır ya da Chrome'dan çıkar.

    Yoklama sayısı `is_connected` çağrısıyla ölçülür (eski kod döngüde `storage_state`
    hiç çağırmıyordu; ona bağlansaydı eski kod sonsuz döngüye girerdi).
    """
    orijinal = tarayici.is_connected
    yoklama = {"n": 0}

    def is_connected() -> bool:
        assert tarayici.context is not None
        yoklama["n"] += 1
        if yoklama["n"] > sonra:
            if kopar:
                tarayici.connected = False
            else:
                tarayici.context.pages.clear()
        return orijinal()

    tarayici.is_connected = is_connected  # type: ignore[method-assign]


async def test_pencere_kapaninca_oturum_yeni_profile_yazilir(sahte, depo):
    tarayici, pw = sahte
    _kullanici(tarayici, kopar=False)

    ozet = await profile_login.open_profile_login(depo, "yeni", "https://example.com/login")

    assert pw.headless is False
    assert tarayici.closed is True
    assert ozet.source == "giris" and ozet.cookie_count == 1 and ozet.allowed_domains == ()
    durum = depo.storage_state("yeni")
    assert durum["cookies"][0]["value"].startswith(GIZLI)
    assert durum["origins"][0]["localStorage"][0]["value"] == "J"


async def test_baglanti_koparsa_son_anlik_goruntu_kaydedilir(sahte, depo):
    """Ölçüldü: Cmd+Q ile çıkışta `is_connected()` False olunca 'oturum kaydedilmedi'
    fırlatılıyordu; yeni giriş çerezleri kayboluyordu."""
    tarayici, _ = sahte
    _kullanici(tarayici, kopar=True)

    ozet = await profile_login.open_profile_login(depo, "yeni", "https://example.com/login")

    assert ozet.cookie_count == 1
    assert depo.exists("yeni")


async def test_hic_anlik_goruntu_alinamazsa_anlasilir_hata(sahte, depo):
    tarayici, _ = sahte
    tarayici.connected = False  # ilk yoklamadan önce koptu

    with pytest.raises(BrowserProfileError, match="kaydedilmedi"):
        await profile_login.open_profile_login(depo, "yeni", "https://example.com/login")
    assert not depo.exists("yeni")


async def test_var_olan_profil_onay_listesini_koruyarak_tazelenir(sahte, depo):
    tarayici, _ = sahte
    depo.save(
        "is",
        (Cookie(name="eski", value="e", domain=".example.com"),),
        source="dosya",
        allowed_domains=("example.com",),
    )
    _kullanici(tarayici, kopar=False)

    ozet = await profile_login.open_profile_login(depo, "is", "https://example.com/login")

    assert tarayici.context is not None and tarayici.context.storage_state_in is not None
    assert ozet.source == "dosya" and ozet.allowed_domains == ("example.com",)
    assert [c["name"] for c in depo.storage_state("is")["cookies"]] == ["sid"]


async def test_gecersiz_adres_ve_profil_adi_tarayici_acmadan_reddedilir(sahte, depo):
    with pytest.raises(BrowserProfileError, match="http"):
        await profile_login.open_profile_login(depo, "is", "example.com")
    with pytest.raises(BrowserProfileError):
        await profile_login.open_profile_login(depo, "../x", "https://example.com")


def test_cli_login_ozet_basar_ve_hatayi_turkce_gosterir(monkeypatch, depo):
    from fusion_cli.cli import browser_commands
    from fusion_cli.cli.app import app

    monkeypatch.setattr(browser_commands, "default_browser_profile_store", lambda: depo)
    cagrilar: list[tuple[str, str]] = []

    async def sahte_giris(store, name, url):
        cagrilar.append((name, url))
        if name == "bozuk":
            raise BrowserProfileError("Giriş penceresi açılamadı (Hata).")
        return store.save(name, (Cookie(name="sid", value=GIZLI, domain="a.com"),), source="giris")

    monkeypatch.setattr(profile_login, "open_profile_login", sahte_giris)
    runner = CliRunner()

    basari = runner.invoke(app, ["browser", "login", "is", "--url", "https://a.com/login"])
    hata = runner.invoke(app, ["browser", "login", "bozuk", "--url", "https://a.com"])

    assert basari.exit_code == 0, basari.output
    assert "Oturum kaydedildi" in basari.output and GIZLI not in basari.output
    assert cagrilar[0] == ("is", "https://a.com/login")
    assert hata.exit_code == 1 and "açılamadı" in hata.output and "Traceback" not in hata.output


def test_alt_surec_girisi_fusion_hatasini_iz_basmadan_bildirir(monkeypatch, capsys):
    from fusion_cli.core.errors import ConfigError

    def patlat(*_: object) -> None:
        raise ConfigError("Sır deposu çözülemedi")

    monkeypatch.setattr(profile_login.asyncio, "run", patlat)

    assert profile_login._main(["x", "is", "https://a.com"]) == 1
    assert "Sır deposu" in capsys.readouterr().err

"""Süreçler arası paylaşılan Chrome: kilit, kira ve kapanış davranışı."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from fusion_cli.core.window_mode import WindowMode
from fusion_cli.providers.macos_window import UNSUPPORTED_MESSAGE, WindowHideResult
from fusion_cli.providers.web_shared_browser import (
    DEVTOOLS_PORT_FILE,
    LEASE_DIR,
    SharedBrowserError,
    SharedBrowserHooks,
    SharedProfileBrowser,
    chrome_launch_arguments,
    read_endpoint,
    read_window_notice,
)


class _FakeChrome:
    """Başlatılınca port dosyası yazan, kapatılınca ölen sahte Chrome."""

    def __init__(self, *, hide_message: str | None = None, can_hide: bool = True) -> None:
        self.launches = 0
        self.closed: list[str] = []
        self.alive = False
        #: Her başlatmada Chrome'a headless bayrağı verildi mi?
        self.headless_launches: list[bool] = []
        #: Pencere gizleme hangi profiller için çağrıldı?
        self.hidden: list[Path] = []
        #: Doluysa gizleme bu kullanıcı metniyle başarısız olur (ör. izin yok).
        self._hide_message = hide_message
        self._can_hide = can_hide

    def hooks(self, *, prepare=lambda _profile: None) -> SharedBrowserHooks:
        async def launch(profile: Path, headless: bool) -> None:
            self.launches += 1
            self.headless_launches.append(headless)
            # Gerçek Chrome gibi portu biraz gecikmeyle yazar.
            await asyncio.sleep(0.01)
            (profile / DEVTOOLS_PORT_FILE).write_text("41234\n/devtools/browser/x\n")
            self.alive = True

        async def is_alive(_endpoint: str) -> bool:
            return self.alive

        async def close(endpoint: str) -> None:
            self.closed.append(endpoint)
            self.alive = False

        async def hide_window(profile: Path) -> WindowHideResult:
            self.hidden.append(profile)
            if self._hide_message is not None:
                return WindowHideResult(is_hidden=False, message=self._hide_message)
            return WindowHideResult(is_hidden=True)

        return SharedBrowserHooks(
            prepare_launch=prepare,
            launch=launch,
            is_alive=is_alive,
            close=close,
            hide_window=hide_window,
            can_hide_window=self._can_hide,
        )


def _dead_pid() -> int:
    process = subprocess.Popen(["true"])
    process.wait()
    return process.pid


def _browser(profile: Path, chrome: _FakeChrome, owner: int) -> SharedProfileBrowser:
    return SharedProfileBrowser(profile, chrome.hooks(), owner_pid=owner)


async def test_ikinci_surec_calisan_chromeu_yeniden_baslatmadan_kullanir(tmp_path):
    chrome = _FakeChrome()

    first = await _browser(tmp_path, chrome, os.getpid()).acquire(headless=True, timeout_s=2)
    second = await _browser(tmp_path, chrome, os.getppid()).acquire(headless=True, timeout_s=2)

    assert first == second == "http://127.0.0.1:41234"
    assert chrome.launches == 1


async def test_ayni_anda_kiralayan_surecler_tek_chrome_baslatir(tmp_path):
    chrome = _FakeChrome()

    await asyncio.gather(
        _browser(tmp_path, chrome, os.getpid()).acquire(headless=True, timeout_s=2),
        _browser(tmp_path, chrome, os.getppid()).acquire(headless=True, timeout_s=2),
    )

    assert chrome.launches == 1


async def test_kiraci_kalirken_birakan_surec_chromeu_kapatmaz(tmp_path):
    chrome = _FakeChrome()
    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=True, timeout_s=2)
    await _browser(tmp_path, chrome, os.getppid()).acquire(headless=True, timeout_s=2)

    await _browser(tmp_path, chrome, os.getpid()).release(force=False, timeout_s=2)

    assert chrome.closed == []
    assert chrome.alive is True


async def test_son_kiraci_birakinca_chrome_kapanir(tmp_path):
    chrome = _FakeChrome()
    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=True, timeout_s=2)

    await _browser(tmp_path, chrome, os.getpid()).release(force=False, timeout_s=2)

    assert chrome.closed == ["http://127.0.0.1:41234"]


async def test_coken_surecin_kirasi_chromeu_acik_tutmaz(tmp_path):
    chrome = _FakeChrome()
    await _browser(tmp_path, chrome, _dead_pid()).acquire(headless=True, timeout_s=2)
    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=True, timeout_s=2)

    await _browser(tmp_path, chrome, os.getpid()).release(force=False, timeout_s=2)

    assert chrome.closed == ["http://127.0.0.1:41234"]


async def test_zorla_birakma_diger_kiracilara_ragmen_chromeu_kapatir(tmp_path):
    """Giriş penceresi profili ister; diğer sekmeler sonraki turda yeniden bağlanır."""
    chrome = _FakeChrome()
    await _browser(tmp_path, chrome, os.getppid()).acquire(headless=True, timeout_s=2)

    await _browser(tmp_path, chrome, os.getpid()).release(force=True, timeout_s=2)

    assert chrome.closed == ["http://127.0.0.1:41234"]
    assert list((tmp_path / LEASE_DIR).iterdir()) == []


async def test_olu_chrome_yerine_yenisi_baslatilir(tmp_path):
    chrome = _FakeChrome()
    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=True, timeout_s=2)
    chrome.alive = False  # Chrome çöktü; port dosyası geride kaldı.

    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=True, timeout_s=2)

    assert chrome.launches == 2


async def test_profil_baska_chromeda_aciksa_hata_tasinir(tmp_path):
    chrome = _FakeChrome()

    def busy(_profile: Path) -> None:
        raise RuntimeError("Bu Fusion Chrome profili hâlâ açık.")

    browser = SharedProfileBrowser(tmp_path, chrome.hooks(prepare=busy), owner_pid=os.getpid())

    with pytest.raises(RuntimeError, match="hâlâ açık"):
        await browser.acquire(headless=True, timeout_s=2)
    assert chrome.launches == 0


async def test_port_dosyasi_gelmezse_acik_hata_verir(tmp_path):
    async def silent_launch(_profile: Path, _headless: bool) -> None:
        return None

    async def never_alive(_endpoint: str) -> bool:
        return False

    async def close(_endpoint: str) -> None:
        return None

    hooks = SharedBrowserHooks(
        prepare_launch=lambda _profile: None,
        launch=silent_launch,
        is_alive=never_alive,
        close=close,
    )
    browser = SharedProfileBrowser(tmp_path, hooks, owner_pid=os.getpid())

    with pytest.raises(SharedBrowserError, match="zamanında açılmadı"):
        await browser.acquire(headless=True, timeout_s=0.2)


async def test_olmayan_profili_birakmak_dizin_olusturmaz(tmp_path):
    chrome = _FakeChrome()
    profile = tmp_path / "yok"

    await _browser(profile, chrome, os.getpid()).release(force=True, timeout_s=1)

    assert not profile.exists()
    assert chrome.closed == []


def test_port_dosyasi_bozuksa_uc_nokta_yoktur(tmp_path):
    (tmp_path / DEVTOOLS_PORT_FILE).write_text("port-degil\n")

    assert read_endpoint(tmp_path) is None


async def test_gizli_kip_chromeu_headless_bayragi_olmadan_acar(tmp_path):
    """Ölçüldü (17 Eylül): headless Chrome Cloudflare doğrulamasına takılıyor."""
    chrome = _FakeChrome()

    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=WindowMode.HIDDEN, timeout_s=2)

    assert chrome.headless_launches == [False]
    assert chrome.hidden == [tmp_path]


async def test_gizleme_her_kiralamada_yinelenir(tmp_path):
    """Kullanıcı pencereyi elle öne çıkarırsa sonraki kullanımda yeniden gizlenir."""
    chrome = _FakeChrome()
    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=WindowMode.HIDDEN, timeout_s=2)

    await _browser(tmp_path, chrome, os.getppid()).acquire(headless=WindowMode.HIDDEN, timeout_s=2)

    assert chrome.launches == 1, "çalışan Chrome yeniden başlatıldı"
    assert chrome.hidden == [tmp_path, tmp_path]


async def test_gizleme_basarisiz_olsa_da_tur_devam_eder_ve_uyari_birakir(tmp_path):
    """Otomasyon izni yoksa pencere görünür kalır; tur düşmez ama sebep sessizce yutulmaz."""
    chrome = _FakeChrome(hide_message="izin yok: Otomasyon ayarını aç")

    endpoint = await _browser(tmp_path, chrome, os.getpid()).acquire(
        headless=WindowMode.HIDDEN, timeout_s=2
    )

    assert endpoint == "http://127.0.0.1:41234"
    assert chrome.hidden == [tmp_path]
    assert read_window_notice(tmp_path) == "izin yok: Otomasyon ayarını aç"


async def test_gizleme_basarili_olunca_eski_uyari_silinir(tmp_path):
    await _browser(tmp_path, _FakeChrome(hide_message="izin yok"), os.getpid()).acquire(
        headless=WindowMode.HIDDEN, timeout_s=2
    )

    await _browser(tmp_path, _FakeChrome(), os.getpid()).acquire(
        headless=WindowMode.HIDDEN, timeout_s=2
    )

    assert read_window_notice(tmp_path) is None


async def test_gizlenemeyen_platformda_gizli_kip_gorunmeze_duser(tmp_path):
    """macOS dışında sessizce görünür pencere açılmaz; görünmez kip + açık uyarı."""
    chrome = _FakeChrome(can_hide=False)

    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=WindowMode.HIDDEN, timeout_s=2)

    assert chrome.headless_launches == [True], "gizlenemeyen pencere açıldı"
    assert chrome.hidden == []
    assert read_window_notice(tmp_path) == UNSUPPORTED_MESSAGE


async def test_gorunmez_acilmis_chrome_gizlenmeye_calisilmaz(tmp_path):
    """Başka sekme profili görünmez açtıysa gizlenecek pencere yoktur; sahte uyarı çıkmaz."""
    chrome = _FakeChrome(hide_message="izin yok")
    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=True, timeout_s=2)

    await _browser(tmp_path, chrome, os.getppid()).acquire(headless=WindowMode.HIDDEN, timeout_s=2)

    assert chrome.hidden == []
    assert read_window_notice(tmp_path) is None


async def test_headless_kipte_pencere_gizleme_cagrilmaz(tmp_path):
    chrome = _FakeChrome()

    await _browser(tmp_path, chrome, os.getpid()).acquire(headless=True, timeout_s=2)

    assert chrome.headless_launches == [True]
    assert chrome.hidden == []


def test_chrome_komutu_otomasyon_bayragi_tasimaz_ve_portu_isletim_sistemine_birakir(tmp_path):
    arguments = chrome_launch_arguments("/chrome", tmp_path, headless=True)

    assert arguments[0] == "/chrome"
    assert f"--user-data-dir={tmp_path}" in arguments
    assert "--remote-debugging-port=0" in arguments
    assert "--headless=new" in arguments
    assert not any("enable-automation" in argument for argument in arguments)


async def test_yeni_sekmeden_sonra_gizli_pencere_yeniden_gizlenir(tmp_path):
    """Ölçüldü: CDP ile yeni sekme açmak gizli Chrome penceresini öne getiriyor."""
    chrome = _FakeChrome()
    shared = _browser(tmp_path, chrome, os.getpid())
    await shared.acquire(headless=WindowMode.HIDDEN, timeout_s=2)

    await shared.reassert_window(headless=WindowMode.HIDDEN)

    assert chrome.hidden == [tmp_path, tmp_path]


@pytest.mark.parametrize("kip", [WindowMode.HEADLESS, WindowMode.VISIBLE])
async def test_gizli_olmayan_kipte_yeni_sekme_pencereye_dokunmaz(tmp_path, kip):
    chrome = _FakeChrome()
    shared = _browser(tmp_path, chrome, os.getpid())
    await shared.acquire(headless=kip, timeout_s=2)

    await shared.reassert_window(headless=kip)

    assert chrome.hidden == []

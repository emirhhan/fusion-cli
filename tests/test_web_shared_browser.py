"""Süreçler arası paylaşılan Chrome: kilit, kira ve kapanış davranışı."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from fusion_cli.providers.web_shared_browser import (
    DEVTOOLS_PORT_FILE,
    LEASE_DIR,
    SharedBrowserError,
    SharedBrowserHooks,
    SharedProfileBrowser,
    chrome_launch_arguments,
    read_endpoint,
)


class _FakeChrome:
    """Başlatılınca port dosyası yazan, kapatılınca ölen sahte Chrome."""

    def __init__(self) -> None:
        self.launches = 0
        self.closed: list[str] = []
        self.alive = False

    def hooks(self, *, prepare=lambda _profile: None) -> SharedBrowserHooks:
        async def launch(profile: Path, _headless: bool) -> None:
            self.launches += 1
            # Gerçek Chrome gibi portu biraz gecikmeyle yazar.
            await asyncio.sleep(0.01)
            (profile / DEVTOOLS_PORT_FILE).write_text("41234\n/devtools/browser/x\n")
            self.alive = True

        async def is_alive(_endpoint: str) -> bool:
            return self.alive

        async def close(endpoint: str) -> None:
            self.closed.append(endpoint)
            self.alive = False

        return SharedBrowserHooks(
            prepare_launch=prepare, launch=launch, is_alive=is_alive, close=close
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


def test_chrome_komutu_otomasyon_bayragi_tasimaz_ve_portu_isletim_sistemine_birakir(tmp_path):
    arguments = chrome_launch_arguments("/chrome", tmp_path, headless=True)

    assert arguments[0] == "/chrome"
    assert f"--user-data-dir={tmp_path}" in arguments
    assert "--remote-debugging-port=0" in arguments
    assert "--headless=new" in arguments
    assert not any("enable-automation" in argument for argument in arguments)

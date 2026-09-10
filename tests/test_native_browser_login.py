"""Kullanıcının elle giriş yaptığı normal Chrome başlatıcısı."""

from unittest.mock import AsyncMock, Mock

import pytest

from fusion_cli.providers import web_browser


async def test_macos_girisi_otomasyon_bayraklari_olmadan_izole_profili_acar(tmp_path, monkeypatch):
    monkeypatch.setattr(web_browser, "_native_login_executable", lambda: "/Chrome")
    monkeypatch.setattr(web_browser, "browser_profile_dir", lambda *_: tmp_path)
    process = AsyncMock()
    process.wait.return_value = 0
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr(web_browser.asyncio, "create_subprocess_exec", launch)
    stop_stale = AsyncMock()
    monkeypatch.setattr(web_browser, "_stop_profile_process", stop_stale, raising=False)

    await web_browser.open_login_browser("gemini_web", "main")

    stop_stale.assert_awaited_once_with(tmp_path)
    assert launch.call_args.args == (
        "/Chrome",
        f"--user-data-dir={tmp_path}",
        "https://gemini.google.com/app",
    )
    process.wait.assert_awaited_once()


async def test_normal_chrome_baslatma_hatasi_basarili_giris_sayilmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(web_browser, "_native_login_executable", lambda: "/Chrome")
    monkeypatch.setattr(web_browser, "browser_profile_dir", lambda *_: tmp_path)
    process = AsyncMock()
    process.wait.return_value = 1
    monkeypatch.setattr(
        web_browser.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr(web_browser, "_stop_profile_process", AsyncMock(), raising=False)

    with pytest.raises(web_browser.WebBrowserError, match="Chrome"):
        await web_browser.open_login_browser("gemini_web", "main")


async def test_url_acik_profile_devredilince_profil_kapanmadan_bitmez(tmp_path, monkeypatch):
    monkeypatch.setattr(web_browser, "_native_login_executable", lambda: "/Chrome")
    monkeypatch.setattr(web_browser, "browser_profile_dir", lambda *_: tmp_path)
    process = AsyncMock()
    process.wait.return_value = 0
    monkeypatch.setattr(
        web_browser.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr(web_browser, "_stop_profile_process", AsyncMock(), raising=False)
    alive = Mock(side_effect=[False, True, True, False])
    monkeypatch.setattr(web_browser, "_profile_process_alive", alive)
    sleep = AsyncMock()
    monkeypatch.setattr(web_browser.asyncio, "sleep", sleep)

    await web_browser.open_login_browser("gemini_web", "main")

    assert sleep.await_count == 2
    assert alive.call_count == 4

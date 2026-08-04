"""Native browser-backed web provider primitives (no real account/network)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.types import Message
from fusion_cli.providers.web_browser import (
    WEB_BROWSER_PROVIDERS,
    browser_profile_dir,
    clear_profile_singletons,
    format_browser_prompt,
    parse_cookie_header,
    web_secret_name,
    _raise_known_page_error,
    WebBrowserAuthError,
)


def test_cookie_header_degerindeki_esittir_isaretini_korur():
    parsed = parse_cookie_header("a=1; session=abc==; empty=; flag")
    assert parsed == {"a": "1", "session": "abc==", "empty": ""}


def test_browser_prompt_tum_kanonik_gecmisi_ve_tool_sonucunu_tasir():
    prompt = format_browser_prompt(
        (
            Message("system", "kurallar"),
            Message("user", "dosyayı oku"),
            Message("tool", "içerik", name="read_file", ok=True),
        )
    )
    assert "### SİSTEM" in prompt
    assert "### KULLANICI" in prompt
    assert "ARAÇ SONUCU (read_file, başarılı)" in prompt
    assert "içerik" in prompt


def test_dort_native_web_saglayicisi_tanimli():
    assert set(WEB_BROWSER_PROVIDERS) == {
        "chatgpt_web",
        "claude_web",
        "gemini_web",
        "copilot_web",
    }
    assert all(item.input_selectors for item in WEB_BROWSER_PROVIDERS.values())
    assert all(item.response_selectors for item in WEB_BROWSER_PROVIDERS.values())


def test_secret_adi_ve_profil_yolu_guvenli_slug_kullanir(monkeypatch, tmp_path):
    monkeypatch.setattr("fusion_cli.providers.web_browser.user_data_dir", lambda: tmp_path)
    assert web_secret_name("chatgpt_web", "kişisel hesap") == (
        "WEB_SECRET::chatgpt_web::ki-isel-hesap"
    )
    assert browser_profile_dir("chatgpt_web", "kişisel hesap") == (
        tmp_path / "web_profiles" / "chatgpt_web" / "ki-isel-hesap"
    )


def test_clear_profile_singletons_takili_kilitleri_siler(tmp_path):
    # Chrome, çökme/zorla kapatma sonrası bu sembolik bağlantıları geride bırakır ve
    # bir sonraki başlatmada "mevcut oturuma devret" moduna girip hemen kapanır.
    (tmp_path / "SingletonLock").symlink_to("unknown-host-2311")
    (tmp_path / "SingletonCookie").symlink_to("3427299203296085704")
    (tmp_path / "SingletonSocket").symlink_to("/var/folders/tmp/SingletonSocket")
    (tmp_path / "Default").mkdir()

    clear_profile_singletons(tmp_path)

    assert not (tmp_path / "SingletonLock").exists()
    assert not (tmp_path / "SingletonLock").is_symlink()
    assert not (tmp_path / "SingletonCookie").is_symlink()
    assert not (tmp_path / "SingletonSocket").is_symlink()
    # Profilin geri kalanına dokunulmaz.
    assert (tmp_path / "Default").is_dir()


def test_clear_profile_singletons_olmayan_dizinde_patlamaz(tmp_path):
    clear_profile_singletons(tmp_path / "yok")


def test_web_session_varsayilanlari_browser_icin_genisletilebilir():
    base = WebSessionConfig(model="custom", endpoint="http://x/v1")
    browser = replace(
        base,
        model="chatgpt_web/main/auto",
        endpoint="",
        provider="chatgpt_web",
        transport="browser",
        credential_ref="WEB_SECRET::chatgpt_web::main",
        tool_support="emulated",
    )
    assert browser.transport == "browser"
    assert browser.tool_support == "emulated"
    assert browser.endpoint == ""


class _FakeLocator:
    def __init__(self, *, text: str = "", visible: bool = False):
        self._text = text
        self._visible = visible
        self.last = self

    async def inner_text(self, timeout=0):
        return self._text

    async def count(self):
        return 1 if self._visible else 0

    async def is_visible(self):
        return self._visible


class _FakePage:
    def __init__(self, url: str, body: str, visible_selectors=()):
        self.url = url
        self._body = body
        self._visible = set(visible_selectors)

    def locator(self, selector):
        if selector == "body":
            return _FakeLocator(text=self._body, visible=True)
        return _FakeLocator(visible=selector in self._visible)


async def test_gemini_bodyde_sign_in_metni_tek_basina_auth_sayilmaz():
    page = _FakePage(
        "https://gemini.google.com/app",
        "Gemini Sign in terms and privacy",
    )
    await _raise_known_page_error(page, WEB_BROWSER_PROVIDERS["gemini_web"])


async def test_gemini_accounts_url_gercek_auth_sinyalidir():
    page = _FakePage(
        "https://accounts.google.com/v3/signin/identifier",
        "Choose an account",
    )
    with pytest.raises(WebBrowserAuthError):
        await _raise_known_page_error(page, WEB_BROWSER_PROVIDERS["gemini_web"])

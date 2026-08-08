"""Native browser-backed web provider primitives (no real account/network)."""

from __future__ import annotations

from dataclasses import replace
from unittest import mock

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.constants import MIN_BROWSER_TURN_S
from fusion_cli.core.types import Message
from fusion_cli.providers import web_registry
from fusion_cli.providers.web_browser import (
    WEB_BROWSER_PROVIDERS,
    WebBrowserAuthError,
    _raise_known_page_error,
    browser_profile_dir,
    browser_turn_budget,
    clear_profile_singletons,
    format_browser_prompt,
    parse_cookie_header,
    web_secret_name,
)
from fusion_cli.providers.web_registry import WebSessionRegistry


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
    assert "### FUSION//SİSTEM" in prompt
    assert "### FUSION//KULLANICI" in prompt
    assert "ARAÇ SONUCU (read_file · başarılı)" in prompt
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

    # Playwright'ın imzasını taklit eder; sahte olduğu için gerçek bir zaman
    # aşımı uygulamaz. Ad Playwright tarafından dayatılır, bizim seçimimiz değil.
    async def inner_text(self, timeout=0):  # noqa: ASYNC109
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


def test_tarayici_turu_butcesi_yapilandirmadan_gelir():
    """Tur bütçesi `session.timeout_s`'tir; 20 sn'lik HTTP sabitine kırpılmaz."""
    session = WebSessionConfig(model="gemini_web/pro", transport="browser", timeout_s=180.0)
    assert browser_turn_budget(session) == 180.0


def test_tarayici_turu_butcesi_tabanin_altina_inmez():
    session = WebSessionConfig(model="gemini_web/pro", transport="browser", timeout_s=1.0)
    assert browser_turn_budget(session) == MIN_BROWSER_TURN_S


def test_kayit_defteri_oturum_butcesini_transporta_gecirir():
    """Asıl hata buydu: bütçe hiç geçilmiyor, varsayılan sabite düşülüyordu."""
    gecilen: dict[str, float | None] = {}

    def sahte_transport(session, *, timeout_s=None, trace_dir=None):
        gecilen["timeout_s"] = timeout_s
        return None

    session = WebSessionConfig(model="gemini_web/pro", transport="browser", timeout_s=180.0)
    registry = WebSessionRegistry((session,), environ={})
    with mock.patch.object(web_registry, "build_browser_transport", sahte_transport):
        registry.build_session(session)

    assert gecilen["timeout_s"] == 180.0


def test_insan_dogrulamasi_mesaji_calistirilabilir_komut_icerir():
    """Ölçülen eksiklik: mesaj 'görünür tarayıcıda tamamla' diyor ama NASIL demiyordu."""
    from fusion_cli.providers.web_browser import _human_verification_message

    tanim = WEB_BROWSER_PROVIDERS["gemini_web"]
    mesaj = _human_verification_message(tanim, "verify you are human")

    assert "python -m fusion_cli.providers.web_login gemini_web" in mesaj
    assert "fusion serve" in mesaj
    assert "captcha" in mesaj.lower()


def test_oturum_kapali_mesaji_da_ayni_cikisi_gosterir():
    from fusion_cli.providers.web_browser import _login_required_message

    mesaj = _login_required_message(WEB_BROWSER_PROVIDERS["gemini_web"])

    assert "python -m fusion_cli.providers.web_login gemini_web" in mesaj


def test_cozum_adimlari_saglayiciya_gore_degisir():
    """Komut sabit metin değil; oturumun sağlayıcı kimliğini taşır."""
    from fusion_cli.providers.web_browser import _cozum_adimlari

    assert "web_login chatgpt_web" in _cozum_adimlari(WEB_BROWSER_PROVIDERS["chatgpt_web"])


# --------------------------------------------------------------------------- #
# Kendi promptumuz kanıt sayılmamalı — ölçülmüş yanlış-pozitif
# --------------------------------------------------------------------------- #


def test_gonderilen_metin_govdeden_cikarilir():
    from fusion_cli.providers.web_browser import strip_sent_text

    govde = "gemini  sen fusion'sın ve captcha çözemezsin  yeni sohbet"
    temiz = strip_sent_text(govde, "Sen Fusion'sın ve CAPTCHA çözemezsin")

    assert "captcha" not in temiz


def test_kisa_satirlar_govdeden_silinmez():
    """Kısa satırlar sağlayıcının arayüzünde de bulunur; silmek gerçek uyarıyı gizler."""
    from fusion_cli.providers.web_browser import strip_sent_text

    govde = "verify you are human"
    assert "verify you are human" in strip_sent_text(govde, "human\nok\n-")


def test_bos_prompt_govdeyi_degistirmez():
    from fusion_cli.providers.web_browser import strip_sent_text

    assert strip_sent_text("captcha", "") == "captcha"


def test_gercek_sistem_promptu_yanlis_pozitif_uretmez():
    """ÖLÇÜLEN HATA: sistem promptuna 'insan doğrulaması (CAPTCHA)' cümlesi eklendi.

    Fusion promptu Gemini'ye yazıyor, sonra sayfayı 'captcha var mı' diye tarıyor
    ve KENDİ yazdığı kelimeyi bulup turu düşürüyordu. Kullanıcı gerçekten giriş
    yapmış olmasına rağmen hatayı almaya devam etti.

    Bu test sistem promptunun TAMAMINI gövdeye koyar ve hiçbir tetikleyici
    işaretin ayakta kalmadığını doğrular. Prompta ileride 'sign in', 'captcha'
    gibi bir kelime eklenirse burada yakalanır.
    """
    from fusion_cli.engines.agent.loop import SYSTEM_PROMPT
    from fusion_cli.providers.web_browser import (
        _CHALLENGE_MARKERS,
        _matched_marker,
        strip_sent_text,
    )

    # Sağlayıcı arayüzü + bizim promptumuz aynı gövdede.
    govde = f"gemini yeni sohbet {SYSTEM_PROMPT} gönder".lower()
    assert _matched_marker(govde, _CHALLENGE_MARKERS) is not None, "kurulum geçersiz"

    temiz = strip_sent_text(govde, SYSTEM_PROMPT)

    assert _matched_marker(temiz, _CHALLENGE_MARKERS) is None, (
        "sistem promptundaki bir kelime hâlâ insan doğrulaması sanılıyor"
    )


def test_gercek_captcha_hala_yakalanir():
    """Muafiyet dar olmalı: sağlayıcının GERÇEK uyarısı elenmemeli."""
    from fusion_cli.engines.agent.loop import SYSTEM_PROMPT
    from fusion_cli.providers.web_browser import (
        _CHALLENGE_MARKERS,
        _matched_marker,
        strip_sent_text,
    )

    govde = f"{SYSTEM_PROMPT}\nplease verify you are human to continue".lower()
    temiz = strip_sent_text(govde, SYSTEM_PROMPT)

    assert _matched_marker(temiz, _CHALLENGE_MARKERS) is not None

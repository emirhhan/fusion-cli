"""Üçüncü pencere kipi: gizli (gerçek pencere, kullanıcının ekranında görünmez).

Ölçüldü (17 Eylül denetimi): ChatGPT web oturumu görünmez (headless) Chrome'da
Cloudflare doğrulamasına takıldı, 7 turun 7'si düştü. Aynı profil headed Chrome'da
ilk turda çalıştı; Chrome normal açılıp macOS'ta süreç gizlendiğinde pencere ekranda
hiç görünmedi ve yanıt 4,2 saniyede geldi.

Kip kullanıcının yapılandırmasındaki `headless` anahtarında taşınır: eski dosyalar
(`headless: true/false`) hiç dokunulmadan çalışmaya devam eder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from fusion_cli.config.loader import load_config
from fusion_cli.config.models import WebSessionConfig
from fusion_cli.config.writer import write_web_sessions
from fusion_cli.core.window_mode import WindowMode, resolve_window_mode
from fusion_cli.providers import macos_window

from .fakes import make_config

_PID = 4242


def _config_with(tmp_path: Path, headless: object) -> Path:
    path = tmp_path / "config.yaml"
    data = {
        "web_sessions": [
            {
                "model": "chatgpt_web/main/auto",
                "provider": "chatgpt_web",
                "transport": "browser",
                "headless": headless,
            }
        ]
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("yazili", "beklenen"),
    [
        (True, WindowMode.HEADLESS),
        (False, WindowMode.VISIBLE),
        ("hidden", WindowMode.HIDDEN),
        ("headless", WindowMode.HEADLESS),
        ("visible", WindowMode.VISIBLE),
    ],
)
def test_eski_boolean_ve_yeni_metin_ayni_alandan_okunur(tmp_path, yazili, beklenen):
    config = load_config(_config_with(tmp_path, yazili))

    assert config.web_sessions[0].headless is beklenen


def test_gecersiz_kip_sessizce_yutulmaz(tmp_path):
    from fusion_cli.core.errors import ConfigError

    with pytest.raises(ConfigError, match="headless"):
        load_config(_config_with(tmp_path, "gorunmez"))


def test_eski_kipler_dosyaya_boolean_olarak_yazilmaya_devam_eder(tmp_path):
    """Kullanıcının dosyasının biçimi değişmez; yalnız yeni kip metin olur."""
    hedef = tmp_path / "config.yaml"
    oturumlar = (
        WebSessionConfig(model="a", headless=WindowMode.HEADLESS),
        WebSessionConfig(model="b", headless=WindowMode.VISIBLE),
        WebSessionConfig(model="c", headless=WindowMode.HIDDEN),
    )

    write_web_sessions(make_config(web_sessions=oturumlar), hedef)

    yazilan = yaml.safe_load(hedef.read_text(encoding="utf-8"))["web_sessions"]
    assert [kayit["headless"] for kayit in yazilan] == [True, False, "hidden"]


def test_yazilan_kip_geri_okunur(tmp_path):
    hedef = tmp_path / "config.yaml"
    oturum = WebSessionConfig(
        model="chatgpt_web/main/auto",
        provider="chatgpt_web",
        transport="browser",
        headless=WindowMode.HIDDEN,
    )

    write_web_sessions(make_config(web_sessions=(oturum,)), hedef)

    assert load_config(hedef).web_sessions[0].headless is WindowMode.HIDDEN


class _SahteOsascript:
    """`subprocess.run` yerine geçer; komutu kaydeder, istenirse hata verir."""

    def __init__(self, *, returncode: int = 0, error: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self._returncode = returncode
        self._error = error

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        if self._error is not None:
            raise self._error
        return subprocess.CompletedProcess(command, self._returncode, stdout="", stderr="hata")


def _profile_with_lock(tmp_path: Path) -> Path:
    (tmp_path / macos_window.SINGLETON_LOCK_FILE).symlink_to(f"makine-{_PID}")
    return tmp_path


async def test_macosta_pencere_surec_kimligiyle_gizlenir(tmp_path, monkeypatch):
    """Süreç ADIYLA gizlenmez: kullanıcının kendi Chrome'u da aynı adı taşır."""
    sahte = _SahteOsascript()
    monkeypatch.setattr(macos_window.sys, "platform", "darwin")
    monkeypatch.setattr(macos_window.subprocess, "run", sahte)

    sonuc = await macos_window.hide_profile_window(_profile_with_lock(tmp_path))

    assert sonuc.is_hidden
    assert len(sahte.calls) == 1
    komut = sahte.calls[0]
    assert komut[0] == "osascript"
    assert f"unix id is {_PID}" in komut[-1]
    assert "set visible of" in komut[-1]


async def test_macos_disinda_hicbir_komut_calistirilmaz(tmp_path, monkeypatch):
    sahte = _SahteOsascript()
    monkeypatch.setattr(macos_window.sys, "platform", "linux")
    monkeypatch.setattr(macos_window.subprocess, "run", sahte)

    sonuc = await macos_window.hide_profile_window(_profile_with_lock(tmp_path))

    assert sahte.calls == []
    assert not sonuc.is_hidden
    assert sonuc.message == macos_window.UNSUPPORTED_MESSAGE


@pytest.mark.parametrize(
    "sahte",
    [
        _SahteOsascript(returncode=1),
        _SahteOsascript(error=OSError("osascript yok")),
        _SahteOsascript(error=subprocess.TimeoutExpired("osascript", 5.0)),
    ],
)
async def test_gizleme_basarisizligi_hata_firlatmaz_ama_turkce_sebep_doner(
    tmp_path, monkeypatch, sahte
):
    """Otomasyon izni yoksa pencere görünür kalır; tur devam eder, sebep kullanıcıya gider."""
    monkeypatch.setattr(macos_window.sys, "platform", "darwin")
    monkeypatch.setattr(macos_window.subprocess, "run", sahte)

    sonuc = await macos_window.hide_profile_window(_profile_with_lock(tmp_path))

    assert not sonuc.is_hidden
    assert sonuc.message == macos_window.HIDE_FAILED_MESSAGE
    assert "Otomasyon" in sonuc.message


async def test_surec_kimligi_okunamazsa_tur_devam_eder(tmp_path, monkeypatch):
    sahte = _SahteOsascript()
    monkeypatch.setattr(macos_window.sys, "platform", "darwin")
    monkeypatch.setattr(macos_window.subprocess, "run", sahte)
    monkeypatch.setattr(macos_window, "PID_WAIT_S", 0.0)

    sonuc = await macos_window.hide_profile_window(tmp_path)

    assert sahte.calls == []
    assert sonuc.message == macos_window.PID_UNKNOWN_MESSAGE


@pytest.mark.parametrize("kip", list(WindowMode))
def test_gizleyebilen_platformda_kip_aynen_kalir(kip):
    assert resolve_window_mode(kip, can_hide=True) is kip


def test_gizleyemeyen_platformda_gizli_kip_gorunmeze_duser():
    """Sessizce görünür pencere açmak kabul edilemez; görünmez kip pencere açmaz."""
    assert resolve_window_mode(WindowMode.HIDDEN, can_hide=False) is WindowMode.HEADLESS


@pytest.mark.parametrize("kip", [WindowMode.VISIBLE, WindowMode.HEADLESS])
def test_gizleyemeyen_platformda_diger_kipler_degismez(kip):
    assert resolve_window_mode(kip, can_hide=False) is kip


def test_panel_karti_pencere_kipini_ve_gizleme_uyarisini_tasir(tmp_path, monkeypatch):
    """Gizleme başarısız olursa sebep panelde görünür; sessizce yutulmaz."""
    from fusion_cli.providers import web_control
    from fusion_cli.providers.web_shared_browser import WINDOW_NOTICE_FILE

    monkeypatch.setattr(
        web_control, "browser_profile_dir", lambda provider, account: tmp_path / provider
    )
    (tmp_path / "chatgpt_web").mkdir()
    (tmp_path / "chatgpt_web" / WINDOW_NOTICE_FILE).write_text(
        macos_window.HIDE_FAILED_MESSAGE, encoding="utf-8"
    )
    oturum = WebSessionConfig(
        model="chatgpt_web/main/auto",
        provider="chatgpt_web",
        transport="browser",
        headless=WindowMode.HIDDEN,
    )

    kartlar = {
        kart["id"]: kart
        for kart in web_control.provider_cards(sessions=(oturum,), secret_store=None)
    }

    assert kartlar["chatgpt_web"]["pencere_kipi"] == "hidden"
    assert kartlar["chatgpt_web"]["pencere_uyarisi"] == macos_window.HIDE_FAILED_MESSAGE
    assert kartlar["claude_web"]["pencere_kipi"] == "headless"
    assert kartlar["claude_web"]["pencere_uyarisi"] is None

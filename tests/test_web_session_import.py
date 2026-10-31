"""Web MODEL oturumundan ajan tarayıcı profiline tek yönlü kopya (P-023).

Gerçek Chrome, Playwright, Keychain ve kullanıcı dizinine DOKUNULMAZ: web profil kökü
`tmp_path`'e çevrilir, paylaşılan Chrome sahte kancalarla, CDP sahte Playwright nesneleriyle
kurulur. Çerez değeri (`GIZLI`) hiçbir çıktıda, logda ya da RPC özetinde görünmemeli.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from fusion_cli.appserver import browser_profiles as rpc
from fusion_cli.cli import browser_commands
from fusion_cli.cli.app import app
from fusion_cli.cli.repl import web_session_command
from fusion_cli.config.browser_profiles import SOURCE_WEB_SESSION, BrowserProfileStore
from fusion_cli.core.cookie_files import internal_domain_reason
from fusion_cli.core.errors import BrowserProfileError
from fusion_cli.engines import web_session_import as engine
from fusion_cli.providers import web_session_export
from fusion_cli.providers.web_browser import WebBrowserError
from fusion_cli.providers.web_shared_browser import (
    DEVTOOLS_PORT_FILE,
    LEASE_DIR,
    SharedBrowserHooks,
    SharedProfileBrowser,
)

GIZLI = "abonelik-cerezi-GIZLI-91"
DURUM = {
    "cookies": [
        {"name": "__Secure-next-auth", "value": GIZLI, "domain": ".chatgpt.com", "path": "/"},
        {"name": "oai", "value": "x", "domain": "auth.openai.com", "path": "/"},
        {"name": "NID", "value": "g", "domain": ".google.com", "path": "/"},
    ],
    "origins": [
        {"origin": "https://chatgpt.com", "localStorage": [{"name": "t", "value": GIZLI}]},
        {"origin": "https://accounts.google.com", "localStorage": [{"name": "g", "value": "1"}]},
    ],
}
runner = CliRunner()


@pytest.fixture
def web_koku(tmp_path, monkeypatch):
    kok = tmp_path / "web_profiles"
    monkeypatch.setattr(
        web_session_export,
        "web_profile_dir",
        lambda provider, account: kok / provider / account,
    )
    profil = kok / "chatgpt_web" / "main"
    (profil / "Default" / "Network").mkdir(parents=True)
    baglanti = sqlite3.connect(profil / "Default" / "Network" / "Cookies")
    baglanti.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
    for host in (".chatgpt.com", "auth.openai.com", ".google.com"):
        baglanti.execute("INSERT INTO cookies VALUES (?, 'n')", (host,))
    baglanti.commit()
    baglanti.close()
    return profil


@pytest.fixture
def depo(tmp_path):
    return BrowserProfileStore(tmp_path / "bp", secret_key="anahtar", clock=lambda: 1.0)


async def _okuyucu(_profile: Path) -> dict[str, object]:
    return DURUM


# --------------------------------------------------------------------------- #
# İç ağ koruması


@pytest.mark.parametrize(
    "alan",
    ["localhost", "app.localhost", "192.168.1.10", "10.0.0.1", "nas.local", "intranet", "com"],
)
def test_ic_ag_ve_tek_etiketli_alan_adi_reddedilir(alan):
    assert internal_domain_reason(alan) is not None


@pytest.mark.parametrize("alan", ["chatgpt.com", ".claude.ai", "sub.example.co.uk", "8.8.8.8"])
def test_genel_alan_adi_kabul_edilir(alan):
    assert internal_domain_reason(alan) is None


# --------------------------------------------------------------------------- #
# Akış (engine)


def test_aktarma_yalniz_secilen_alan_adlarini_onay_listesiyle_yazar(web_koku, depo):
    kaynak = engine.find_web_session("chatgpt")

    ozet = asyncio.run(
        engine.import_web_session(depo, kaynak, "gpt", ("chatgpt.com",), reader=_okuyucu)
    )

    assert ozet.source == SOURCE_WEB_SESSION
    assert ozet.allowed_domains == ("chatgpt.com",)
    assert ozet.domains == ("chatgpt.com",)
    durum = depo.storage_state("gpt")
    assert [c["domain"] for c in durum["cookies"]] == [".chatgpt.com"]
    assert [o["origin"] for o in durum["origins"]] == ["https://chatgpt.com"]


def test_aktarma_alan_adi_olmadan_ve_ic_ag_adiyla_reddedilir(web_koku, depo):
    kaynak = engine.find_web_session("chatgpt_web")
    okundu: list[Path] = []

    async def okuyucu(profile: Path) -> dict[str, object]:
        okundu.append(profile)
        return DURUM

    for alanlar in ((), None, ("localhost",), ("192.168.1.1",), ("com",)):
        with pytest.raises(BrowserProfileError):
            asyncio.run(engine.import_web_session(depo, kaynak, "gpt", alanlar, reader=okuyucu))
    assert okundu == []
    assert not depo.exists("gpt")


def test_anahtar_yoksa_oturuma_hic_baglanilmaz(web_koku, tmp_path):
    depo = BrowserProfileStore(tmp_path / "bp", secret_key=None)
    okundu: list[Path] = []

    async def okuyucu(profile: Path) -> dict[str, object]:
        okundu.append(profile)
        return DURUM

    with pytest.raises(BrowserProfileError, match="anahtar"):
        asyncio.run(
            engine.import_web_session(
                depo, engine.find_web_session("chatgpt"), "gpt", ("chatgpt.com",), reader=okuyucu
            )
        )
    assert okundu == []


def test_eslesen_cerez_yoksa_hicbir_sey_yazilmaz(web_koku, depo):
    with pytest.raises(BrowserProfileError, match="eşleşen"):
        asyncio.run(
            engine.import_web_session(
                depo, engine.find_web_session("chatgpt"), "gpt", ("bank.com",), reader=_okuyucu
            )
        )
    assert not depo.exists("gpt")


def test_bilinmeyen_saglayici_ve_olmayan_oturum_turkce_hata(web_koku):
    with pytest.raises(BrowserProfileError, match="Bilinmeyen web sağlayıcısı"):
        engine.find_web_session("netflix")
    with pytest.raises(BrowserProfileError, match="web-login"):
        engine.find_web_session("claude")


def test_onizleme_sifre_cozmeden_alan_adlarini_verir(web_koku):
    onizleme = engine.preview_web_session(engine.find_web_session("chatgpt"), ("openai.com",))

    assert onizleme.domains == ("auth.openai.com", "chatgpt.com", "google.com")
    assert onizleme.matching == ("auth.openai.com",)
    assert [(s.provider, s.account) for s in engine.available_web_sessions()] == [
        ("chatgpt_web", "main")
    ]


# --------------------------------------------------------------------------- #
# Paylaşılan Chrome'dan okuma: açık web oturumu bozulmaz


class _SahteChrome:
    def __init__(self, *, calisiyor: bool) -> None:
        self.alive = calisiyor
        self.launches = 0
        self.closed: list[str] = []

    def hooks(self, prepare=lambda _profile: None) -> SharedBrowserHooks:
        async def launch(profile: Path, _headless: bool) -> None:
            self.launches += 1
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


class _Baglam:
    async def storage_state(self) -> dict[str, object]:
        return DURUM


class _Tarayici:
    def __init__(self) -> None:
        self.contexts = [_Baglam()]
        self.kapandi = False

    async def close(self) -> None:
        self.kapandi = True


class _Chromium:
    def __init__(self) -> None:
        self.baglantilar: list[str] = []
        self.tarayici = _Tarayici()

    async def connect_over_cdp(self, endpoint: str) -> _Tarayici:
        self.baglantilar.append(endpoint)
        return self.tarayici


class _Playwright:
    def __init__(self) -> None:
        self.chromium = _Chromium()


def _oku(profil: Path, chrome: _SahteChrome, pw: _Playwright, prepare=lambda _p: None):
    @contextlib.asynccontextmanager
    async def baslat():
        yield pw

    return asyncio.run(
        web_session_export.read_web_session_state(
            profil,
            timeout_s=2.0,
            shared_factory=lambda _pw, path: SharedProfileBrowser(
                path, chrome.hooks(prepare), owner_pid=os.getpid()
            ),
            playwright_factory=baslat,
        )
    )


def _canli_baska_surec() -> subprocess.Popen[bytes]:
    return subprocess.Popen(["sleep", "30"])


def test_acik_oturuma_katilir_chromeu_kapatmaz_diger_kirayi_birakir(tmp_path):
    profil = tmp_path / "p"
    (profil / LEASE_DIR).mkdir(parents=True)
    (profil / DEVTOOLS_PORT_FILE).write_text("41234\n/devtools/browser/x\n")
    diger = _canli_baska_surec()
    try:
        (profil / LEASE_DIR / str(diger.pid)).touch()
        chrome = _SahteChrome(calisiyor=True)
        pw = _Playwright()

        durum = _oku(profil, chrome, pw)

        assert durum is DURUM
        assert chrome.launches == 0 and chrome.closed == []
        assert (profil / LEASE_DIR / str(diger.pid)).exists()
        assert not (profil / LEASE_DIR / str(os.getpid())).exists()
        assert pw.chromium.tarayici.kapandi  # yalnız CDP bağlantısı bırakıldı
    finally:
        diger.kill()
        diger.wait()


def test_bu_surecin_kirasi_varsa_birakilmaz(tmp_path):
    profil = tmp_path / "p"
    (profil / LEASE_DIR).mkdir(parents=True)
    (profil / DEVTOOLS_PORT_FILE).write_text("41234\n/devtools/browser/x\n")
    (profil / LEASE_DIR / str(os.getpid())).touch()
    chrome = _SahteChrome(calisiyor=True)

    _oku(profil, chrome, _Playwright())

    assert (profil / LEASE_DIR / str(os.getpid())).exists()
    assert chrome.closed == []


def test_kapali_oturumda_chrome_acilir_okunur_ve_kapatilir(tmp_path):
    profil = tmp_path / "p"
    profil.mkdir()
    chrome = _SahteChrome(calisiyor=False)

    durum = _oku(profil, chrome, _Playwright())

    assert durum is DURUM
    assert chrome.launches == 1
    assert len(chrome.closed) == 1


def test_giris_penceresi_profili_tutuyorsa_anlasilir_hata(tmp_path):
    profil = tmp_path / "p"
    profil.mkdir()

    def acik(_profile: Path) -> None:
        raise WebBrowserError("Bu Fusion Chrome profili hâlâ açık.")

    with pytest.raises(BrowserProfileError, match="bağlanılamadı"):
        _oku(profil, _SahteChrome(calisiyor=False), _Playwright(), prepare=acik)


# --------------------------------------------------------------------------- #
# Yüzeyler: CLI, REPL, RPC — değer hiçbir çıktıda yok


@pytest.fixture
def sahte_okuma(monkeypatch):
    monkeypatch.setattr(engine, "read_web_session_state", _okuyucu)


def test_cli_yes_ile_yazar_degeri_basmaz(web_koku, depo, sahte_okuma, monkeypatch, caplog):
    monkeypatch.setattr(browser_commands, "default_browser_profile_store", lambda: depo)
    caplog.set_level(logging.DEBUG)

    result = runner.invoke(
        app, ["browser", "import-web-session", "chatgpt", "-p", "gpt", "-d", "chatgpt.com", "-y"]
    )

    assert result.exit_code == 0, result.output
    assert "chatgpt.com" in result.output and "abonelik oturumunun" in result.output
    assert GIZLI not in result.output and GIZLI not in caplog.text
    assert depo.summary("gpt").allowed_domains == ("chatgpt.com",)


def test_cli_alan_adi_ve_tty_yokken_yes_zorunlu(web_koku, depo, sahte_okuma, monkeypatch):
    monkeypatch.setattr(browser_commands, "default_browser_profile_store", lambda: depo)

    alansiz = runner.invoke(app, ["browser", "import-web-session", "chatgpt", "-p", "gpt", "-y"])
    onaysiz = runner.invoke(
        app, ["browser", "import-web-session", "chatgpt", "-p", "gpt", "-d", "chatgpt.com"]
    )

    assert alansiz.exit_code == 1 and "alan adı" in alansiz.output
    assert onaysiz.exit_code == 1 and "--yes" in onaysiz.output
    assert not depo.exists("gpt")


def test_cli_web_oturumlarini_listeler(web_koku):
    result = runner.invoke(app, ["browser", "web-sessions"])

    assert result.exit_code == 0, result.output
    assert "chatgpt_web" in result.output


def _repl(argument: str) -> str:
    console = Console(record=True, width=200)
    asyncio.run(web_session_command.run(None, argument, console))  # type: ignore[arg-type]
    return console.export_text()


def test_repl_onaysiz_yalniz_onizler_yes_ile_yazar(web_koku, depo, monkeypatch):
    okundu: list[Path] = []

    async def okuyucu(profile: Path) -> dict[str, object]:
        okundu.append(profile)
        return DURUM

    monkeypatch.setattr(engine, "read_web_session_state", okuyucu)
    monkeypatch.setattr(web_session_command, "_store", lambda: depo)

    onizleme = _repl("chatgpt gpt chatgpt.com")
    assert "--yes" in onizleme and okundu == [] and not depo.exists("gpt")

    sonuc = _repl("chatgpt gpt chatgpt.com --yes")
    assert "Profil yazıldı: gpt" in sonuc and GIZLI not in sonuc
    assert depo.summary("gpt").allowed_domains == ("chatgpt.com",)


def test_repl_kullanim_ve_ic_ag_hatasi(web_koku, depo, monkeypatch):
    monkeypatch.setattr(web_session_command, "_store", lambda: depo)

    assert "Kullanım" in _repl("chatgpt gpt")
    assert "iç ağ" in _repl("chatgpt gpt nas.local --yes")


def test_rpc_onizleme_ve_aktarma_degeri_ozette_tasimaz(web_koku, depo, sahte_okuma):
    liste = rpc.web_sessions({"saglayici": "chatgpt_web", "hesap": "main"})
    assert liste["oturumlar"] == [{"saglayici": "chatgpt_web", "hesap": "main"}]
    assert liste["alan_adlari"] == ["auth.openai.com", "chatgpt.com", "google.com"]

    bos = asyncio.run(rpc.import_from_web_session(depo, {"saglayici": "chatgpt_web", "ad": "g"}))
    assert bos["ok"] is False and "alan adı" in bos["metin"]

    sonuc = asyncio.run(
        rpc.import_from_web_session(
            depo, {"saglayici": "chatgpt_web", "ad": "gpt", "alan_adlari": ["chatgpt.com"]}
        )
    )
    assert sonuc["ok"] is True
    assert sonuc["profil"]["kaynak"] == SOURCE_WEB_SESSION
    assert GIZLI not in repr(sonuc)

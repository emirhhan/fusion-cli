"""Eklenti kurulum yardımcısı: hazırlık, doğrulama ve platform komutları."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fusion_cli.appserver import chrome_host, chrome_install


def _profil(kok: Path, kimlik: str, **bilgi: object) -> None:
    dizin = kok / "Default"
    dizin.mkdir(parents=True, exist_ok=True)
    kayit = {"manifest": {"name": "Fusion Browser", "version": "0.3.11"}, **bilgi}
    (dizin / "Preferences").write_text(
        json.dumps({"extensions": {"settings": {kimlik: kayit}}}), encoding="utf-8"
    )


@pytest.fixture
def chrome_kok(tmp_path, monkeypatch) -> Path:
    kok = tmp_path / "chrome"
    monkeypatch.setattr(chrome_install, "chrome_user_data_dir", lambda home=None: kok)
    return kok


def test_manifest_anahtari_sabit_kimligi_verir():
    import base64
    import hashlib

    manifest = json.loads(
        (
            Path(chrome_install.__file__).resolve().parents[3]
            / "chrome-extension"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    ozet = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    kimlik = "".join(chr(ord("a") + int(harf, 16)) for harf in ozet)
    assert kimlik == chrome_host.FIXED_EXTENSION_ID


def test_yuklu_degilse_yuklu_yok_gorunur(chrome_kok):
    assert chrome_install.install_status()["eklenti_yuklu"] is False


def test_yuklu_ve_etkin_eklenti_dogrulanir(chrome_kok):
    _profil(chrome_kok, chrome_host.FIXED_EXTENSION_ID, state=1)
    durum = chrome_install.install_status()
    assert durum == {"eklenti_yuklu": True, "eklenti_etkin": True, "eklenti_surum": "0.3.11"}


def test_devre_disi_eklenti_yuklu_ama_etkin_degil(chrome_kok):
    _profil(chrome_kok, "x" * 32, state=0, disable_reasons=1)
    durum = chrome_install.install_status()
    assert durum["eklenti_yuklu"] is True
    assert durum["eklenti_etkin"] is False


def test_hazirlik_klasoru_kopyalar_panoya_yazar_ve_chrome_i_acar(tmp_path, monkeypatch, chrome_kok):
    monkeypatch.setattr(chrome_install, "base_config_dir", lambda: tmp_path / "cfg")
    monkeypatch.setattr(chrome_install, "install_native_host", lambda ids, home=None: [])
    monkeypatch.setattr(chrome_install.sys, "platform", "darwin")
    cagrilar: list[tuple[list[str], str | None]] = []

    sonuc = chrome_install.begin_install(lambda komut, girdi: cagrilar.append((komut, girdi)))

    assert sonuc["ok"] is True
    assert (tmp_path / "cfg" / "chrome-extension" / "manifest.json").is_file()
    assert cagrilar[0] == (["pbcopy"], sonuc["yol"])
    assert ["open", "-a", "Google Chrome", "chrome://extensions"] in [c for c, _ in cagrilar]
    assert len(sonuc["adimlar"]) == 3
    assert sonuc["eklenti_yuklu"] is False


def test_desteklenmeyen_sistemde_acik_hata_verir(monkeypatch):
    monkeypatch.setattr(chrome_install.sys, "platform", "linux")
    sonuc = chrome_install.begin_install(lambda *_: None)
    assert sonuc["ok"] is False
    assert "macOS ve Windows" in sonuc["metin"]


def test_windows_komutlari_pano_ve_gezgini_kullanir(tmp_path, monkeypatch):
    monkeypatch.setattr(chrome_install.sys, "platform", "win32")
    komutlar = [c for c, _ in chrome_install._platform_commands(tmp_path)]
    assert ["clip"] in komutlar
    assert ["explorer", str(tmp_path)] in komutlar


def test_kaynak_yoksa_hata_yakalanir(monkeypatch, chrome_kok):
    monkeypatch.setattr(chrome_install, "source_extension_dir", lambda: None)
    monkeypatch.setattr(chrome_install.sys, "platform", "darwin")
    assert chrome_install.begin_install(lambda *_: None)["ok"] is False


def _cevap(kod=0, cikti=""):
    import subprocess

    return subprocess.CompletedProcess([], kod, cikti, "")


def test_otomatik_kurulum_izin_yoksa_ayar_panelini_acar_ve_yonlendirir(chrome_kok):
    from fusion_cli.appserver import chrome_autoinstall as oto

    komutlar: list[list[str]] = []

    def runner(komut):
        komutlar.append(komut)
        return _cevap(0, "false")

    sonuc = oto.auto_install(runner=runner, prepare=lambda home=None: {"ok": True, "yol": "/x"})
    assert sonuc["asama"] == "izin_gerekli" and "Erişilebilirlik" in sonuc["metin"]
    assert ["open", oto.ACCESSIBILITY_PANE] in komutlar


def test_otomatik_kurulum_arayuzu_surer_ve_profilde_dogrular(chrome_kok):
    from fusion_cli.appserver import chrome_autoinstall as oto

    def runner(komut):
        if komut[1] == "-e":
            return _cevap(0, "true")
        _profil(chrome_kok, chrome_host.FIXED_EXTENSION_ID, state=1)
        return _cevap(0, "ok")

    sonuc = oto.auto_install(
        runner=runner,
        prepare=lambda home=None: {"ok": True, "yol": "/x"},
        sleep=lambda _s: None,
    )
    assert sonuc["asama"] == "yuklendi" and sonuc["eklenti_yuklu"] is True


def test_arayuz_adimi_basarisizsa_elle_kuruluma_duser(chrome_kok):
    from fusion_cli.appserver import chrome_autoinstall as oto

    def runner(komut):
        return _cevap(0, "true" if komut[1] == "-e" else "no-switch")

    sonuc = oto.auto_install(runner=runner, prepare=lambda home=None: {"ok": True, "yol": "/x"})
    assert sonuc["asama"] == "elle" and "Geliştirici modu" in sonuc["metin"]


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("osacompile") is None,
    reason="macOS AppleScript derleyicisi gerekli",
)
def test_autoinstall_applescript_derleniyor(tmp_path):
    """Betik sözdizimi hatası (ayrılmış sözcük) sahada 'error' olarak görünüyordu."""
    from fusion_cli.appserver.chrome_autoinstall import _APPLESCRIPT

    kaynak = tmp_path / "kur.applescript"
    kaynak.write_text(_APPLESCRIPT, encoding="utf-8")
    cevap = subprocess.run(
        ["osacompile", "-o", str(tmp_path / "kur.scpt"), str(kaynak)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cevap.returncode == 0, cevap.stderr

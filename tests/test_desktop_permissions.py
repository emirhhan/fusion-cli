"""Erişilebilirlik ve Ekran Kaydı izin akışı: ön kontrol, istem, yapısal sonuç (P-005)."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop, desktop_lock
from fusion_cli.tools import desktop_permissions as izin


class _Framework:
    """Sahte ApplicationServices: hangi C çağrılarının yapıldığını kaydeder."""

    def __init__(self, trusted: bool, screen: bool) -> None:
        self.trusted, self.screen = trusted, screen
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> object:
        parent = self

        class _Fn:
            restype = None
            argtypes = None

            def __call__(self, *args: object) -> bool:
                parent.calls.append(name)
                if name == "AXIsProcessTrusted":
                    return parent.trusted
                if name == "CGPreflightScreenCaptureAccess":
                    return parent.screen
                return False

        return _Fn()


def test_on_kontrol_istem_acmadan_iki_izni_okur(monkeypatch) -> None:
    """Ölçüldü (31 Ekim): Ekran Kaydı hiç yoklanmıyordu; yalnız AXIsProcessTrusted okunuyordu."""
    monkeypatch.setattr(izin.sys, "platform", "darwin")
    framework = _Framework(trusted=True, screen=False)
    monkeypatch.setattr(izin, "_application_services", lambda: framework)

    durum = izin.probe()

    assert durum.accessibility == "granted" and durum.screen_recording == "denied"
    assert "AXIsProcessTrustedWithOptions" not in framework.calls
    assert "CGRequestScreenCaptureAccess" not in framework.calls
    assert durum.as_dict()["ayarlar"]["screen_recording"].endswith("Privacy_ScreenCapture")


def test_macos_disinda_desteklenmiyor(monkeypatch) -> None:
    monkeypatch.setattr(izin.sys, "platform", "linux")
    assert izin.probe().accessibility == "unsupported"
    assert izin.request("accessibility").screen_recording == "unsupported"


def test_istem_dogru_sistem_cagrisini_acar(monkeypatch) -> None:
    monkeypatch.setattr(izin.sys, "platform", "darwin")
    framework = _Framework(trusted=False, screen=False)
    monkeypatch.setattr(izin, "_application_services", lambda: framework)
    acilan: list[str] = []
    monkeypatch.setattr(izin, "_prompt_accessibility", lambda fw: acilan.append("ax") or False)
    monkeypatch.setattr(izin, "_prompt_screen_capture", lambda fw: acilan.append("ekran") or False)

    izin.request("accessibility")
    izin.request("screen_recording")

    assert acilan == ["ax", "ekran"]
    with pytest.raises(ValueError):
        izin.request("kamera")


def test_izin_eksikse_arac_yapisal_sonuc_doner(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop_lock, "claim", lambda **_: None)
    monkeypatch.setattr(desktop, "_framework", lambda: object())
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: False)

    sonuc = desktop.desktop_type({"text": "x"}, ToolContext(root=tmp_path))

    assert not sonuc.ok
    assert sonuc.structured == {
        "izin_gerekli": "accessibility",
        "ayar_baglantisi": izin.SETTINGS_URLS["accessibility"],
    }
    assert izin.missing_permission_from_output(sonuc.output) == "accessibility"
    assert izin.missing_permission_from_output("başka hata") is None


def test_erisilebilirlik_metni_yeniden_acilis_istemez() -> None:
    """Ölçüldü (31 Ekim): metin 'uygulamayı yeniden aç' diyordu; arayüz kartı ve macOS bunu
    istemez, yalnız Ekran Kaydı için gerekebilir."""
    assert "yeniden aç" not in izin.MESSAGES[izin.ACCESSIBILITY]
    assert "yeniden dene" in izin.MESSAGES[izin.ACCESSIBILITY]
    assert "gerekirse" in izin.MESSAGES[izin.SCREEN_RECORDING]
    assert izin.missing_permission_from_output(izin.MESSAGES[izin.ACCESSIBILITY]) == "accessibility"

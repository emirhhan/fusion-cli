"""Reddedilen/engelli uygulamalar modele görünmez: bölge, geri düşüş, listeler (P-007 inceleme).

Gerçek pencereler okunmaz, yardımcı çağrılmaz: yakalama ve pencere listeleri sahte verilir.
"""

from __future__ import annotations

import base64
import json
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from fusion_cli.core.desktop_frame import DesktopFrame
from fusion_cli.core.desktop_settings import DesktopSettings
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop_background, desktop_inspect, desktop_screen, desktop_visibility
from fusion_cli.tools.desktop_screen import Display


def _png(width: int, height: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    return (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + chunk + struct.pack(">I", zlib.crc32(chunk))
    )


@pytest.fixture
def screen(monkeypatch):
    """Ana ekran 1440x900 nokta; `screencapture` komutları kaydedilir."""
    monkeypatch.setattr(desktop_screen, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_screen, "_screen_recording_denied", lambda: False)
    monkeypatch.setattr(
        desktop_screen,
        "list_displays",
        lambda: (Display(1, 0.0, 0.0, 1440.0, 900.0, True, identifier=7),),
    )
    commands: list[list[str]] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[0] == "screencapture":
            Path(command[-1]).write_bytes(_png(200, 100))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(desktop_screen, "_run", fake_run)
    return commands


def _context(tmp_path, **settings) -> ToolContext:
    context = ToolContext(root=tmp_path, desktop_settings=DesktopSettings(**settings))
    context.desktop.frame = DesktopFrame(1440, 900, 0.0, 0.0, 1440.0, 900.0, 1)
    return context


# --------------------------------------------------------------------------- ekran görüntüsü


def test_bolge_yakalama_da_dislamali_yerel_yoldan_gider(tmp_path, monkeypatch, screen):
    """Ölçüldü (31 Ekim): `region=` doğrudan `screencapture -R` idi, ret listesi uygulanmıyordu."""
    calls: list[dict[str, object]] = []

    def fake_invoke(operation: str, target: dict[str, object]) -> dict[str, object]:
        calls.append(target)
        image = base64.b64encode(_png(80, 40)).decode()
        return {"ok": True, "image": "data:image/png;base64," + image}

    monkeypatch.setattr(desktop_screen, "invoke_sync", fake_invoke)
    monkeypatch.setattr(desktop_screen, "_exclude_pids", lambda: [10])
    context = _context(tmp_path, denied_apps=("1Password",))

    result = desktop_screen.desktop_screenshot({"path": "r.png", "region": "100,50,80,40"}, context)

    assert result.ok, result.output
    assert screen == []
    request = calls[0]["request"]
    assert request["rect"] == [100.0, 50.0, 80.0, 40.0]  # type: ignore[index]
    assert "1password" in request["excludeNames"]  # type: ignore[index]


def test_eski_dislama_ayari_kapali_olsa_da_fusion_ve_ret_listesi_dislanir(
    tmp_path, monkeypatch, screen
):
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        desktop_screen, "invoke_sync", lambda operation, target: calls.append(target) or {}
    )
    monkeypatch.setattr(desktop_screen, "_hidden_apps_on_screen", lambda settings: ())
    context = ToolContext(
        root=tmp_path,
        desktop_exclude_fusion_window=False,
        desktop_settings=DesktopSettings(denied_apps=("Notes",)),
    )

    assert desktop_screen.desktop_screenshot({"path": "s.png"}, context).ok
    request = calls[0]["request"]
    assert request["excludePids"] == desktop_screen._exclude_pids()  # type: ignore[index]
    assert "notes" in request["excludeNames"]  # type: ignore[index]


def test_geri_dususte_engelli_uygulama_gorunurse_yakalanmaz(tmp_path, monkeypatch, screen):
    monkeypatch.setattr(desktop_screen, "_native_capture", lambda *_, **__: None)
    monkeypatch.setattr(
        desktop_screen,
        "_hidden_apps_on_screen",
        lambda settings: desktop_visibility.visible_hidden_apps(
            settings, ("Finder", "1Password 7", "Fusion")
        ),
    )
    context = _context(tmp_path, denied_apps=("Mail", "1Password 7"))
    for args in ({"path": "s.png"}, {"path": "s.png", "region": "0,0,10,10"}):
        result = desktop_screen.desktop_screenshot(args, context)
        assert not result.ok and "1Password 7" in result.output
    assert screen == [] and not (tmp_path / "s.png").exists()


def test_geri_dususte_pencereler_okunamazsa_yakalanmaz(tmp_path, monkeypatch, screen):
    monkeypatch.setattr(desktop_screen, "_native_capture", lambda *_, **__: None)
    monkeypatch.setattr(desktop_screen, "_hidden_apps_on_screen", lambda settings: None)

    context = _context(tmp_path, denied_apps=("1Password",))
    result = desktop_screen.desktop_screenshot({"path": "s.png"}, context)

    assert not result.ok and "okunamadı" in result.output and screen == []


def test_geri_dususte_engelli_uygulama_yoksa_ya_da_liste_bossa_yakalanir(
    tmp_path, monkeypatch, screen
):
    monkeypatch.setattr(desktop_screen, "_native_capture", lambda *_, **__: None)
    monkeypatch.setattr(desktop_screen, "_hidden_apps_on_screen", lambda settings: ())
    assert desktop_screen.desktop_screenshot({"path": "a.png"}, _context(tmp_path)).ok
    # Ret listesi boş: denetlenecek bir şey yok, pencereler okunmaz (#425: engelli kategori yok).
    monkeypatch.setattr(desktop_screen, "_hidden_apps_on_screen", lambda settings: None)
    context = _context(tmp_path)
    assert desktop_screen.desktop_screenshot({"path": "b.png"}, context).ok
    assert [command[0] for command in screen] == ["screencapture", "screencapture"]


def test_gorunen_engelli_uygulamalar_fusion_ve_acilanlar_haric():
    # #425: yatırım platformu ve parola yöneticisi engelli değil; yalnız ret listesi gizlenir.
    settings = DesktopSettings(denied_apps=("Mail", "1Password"))
    owners = ("Mail", "Binance", "Fusion", "Notes", "1Password", "")
    assert desktop_visibility.visible_hidden_apps(settings, owners) == ("1Password", "Mail")
    assert desktop_visibility.visible_hidden_apps(settings, None) is None


# --------------------------------------------------------------------------- listeler ve ağaç


def _osascript(monkeypatch, stdout: str) -> None:
    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_inspect, "_framework", lambda: object())
    monkeypatch.setattr(desktop_inspect, "_trusted", lambda framework: True)
    monkeypatch.setattr(
        desktop_inspect.subprocess,
        "run",
        lambda command, **_: subprocess.CompletedProcess(command, 0, stdout, ""),
    )


def test_desktop_windows_engelli_uygulamalari_listelemez(tmp_path, monkeypatch):
    """Ölçüldü (31 Ekim): kasa kaydı başlıkları (1Password penceresi) listede dönüyordu."""
    _osascript(monkeypatch, "Mail\tGelen\n1Password 7\tBanka hesabı\nNotes\tListe\n")
    context = _context(tmp_path, denied_apps=("Notes", "1Password 7"))

    result = desktop_inspect.desktop_windows({}, context)

    assert result.ok and result.output == "Mail\tGelen"


def test_desktop_accessibility_engelli_on_uygulamada_agac_vermez(tmp_path, monkeypatch):
    _osascript(
        monkeypatch,
        "Uygulama: 1Password\nPaket: com.1password.1password\nPencere: Kasa\nAXRow\tBanka\n",
    )
    context = _context(tmp_path, denied_apps=("1Password",))
    result = desktop_inspect.desktop_accessibility({}, context)
    assert not result.ok and "Banka" not in result.output and "1Password" in result.output

    _osascript(monkeypatch, "Uygulama: Notlar\nPaket: com.apple.Notes\nPencere: A\nAXButton\tB\n")
    assert not desktop_inspect.desktop_accessibility(
        {}, _context(tmp_path, denied_apps=("com.apple.notes",))
    ).ok
    assert desktop_inspect.desktop_accessibility({}, _context(tmp_path)).ok


async def test_arka_plan_pencere_listesi_engellileri_gizler(tmp_path, monkeypatch):
    rows = [
        {"kind": "window", "id": 1, "pid": 41, "app": "Mail", "title": "Gelen"},
        {"kind": "window", "id": 2, "pid": 42, "app": "Bitwarden", "title": "Kasa"},
        {"kind": "window", "id": 3, "pid": 43, "app": "Notes", "title": "Liste"},
    ]

    class _Host:
        async def invoke(self, operation, target):
            return {"ok": True, "windows": [dict(row) for row in rows]}

    monkeypatch.setattr(desktop_background, "SwiftDesktop", _Host)

    result = await desktop_background.desktop_background_windows(
        {}, _context(tmp_path, denied_apps=("notes", "Bitwarden"))
    )

    assert [row["app"] for row in json.loads(result.output)["windows"]] == ["Mail"]

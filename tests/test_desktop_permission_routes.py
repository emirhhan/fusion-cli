"""`izin.masaustu_*` uçları ve `MasaustuIzinGerekli` olayı (P-005)."""

from __future__ import annotations

from fusion_cli.appserver.desktop_permission_routes import (
    DESKTOP_PERMISSION_ROUTES,
    DesktopPermissionWatch,
    dispatch_desktop_permission,
)
from fusion_cli.core.events import ToolExecuted, ToolOutcome, TurnFinished
from fusion_cli.tools import desktop_permissions as izin


def test_durum_ucu_istem_acmadan_okur(monkeypatch) -> None:
    istemler: list[str] = []
    monkeypatch.setattr(izin, "request", lambda kind: istemler.append(kind))
    monkeypatch.setattr(izin, "probe", lambda: izin.DesktopPermissionStatus("granted", "denied"))
    import fusion_cli.appserver.desktop_permission_routes as routes

    monkeypatch.setattr(routes, "probe", izin.probe)

    sonuc = dispatch_desktop_permission("izin.masaustu_durum", {})

    assert sonuc["ok"] is True and sonuc["accessibility"] == "granted"
    assert sonuc["screen_recording"] == "denied" and istemler == []
    assert "izin.masaustu_iste" in DESKTOP_PERMISSION_ROUTES


def test_istek_ucu_turu_dogrular_ve_istem_acar(monkeypatch) -> None:
    import fusion_cli.appserver.desktop_permission_routes as routes

    istemler: list[str] = []

    def fake_request(kind: str) -> izin.DesktopPermissionStatus:
        istemler.append(kind)
        return izin.DesktopPermissionStatus("granted", "granted")

    monkeypatch.setattr(routes, "request", fake_request)

    assert dispatch_desktop_permission("izin.masaustu_iste", {"tur": "kamera"})["ok"] is False
    sonuc = dispatch_desktop_permission("izin.masaustu_iste", {"tur": "screen_recording"})

    assert sonuc["ok"] is True and istemler == ["screen_recording"]
    assert dispatch_desktop_permission("izin.bilinmeyen", {})["ok"] is False


def test_izin_yuzunden_dusen_arac_olay_uretir_turda_bir_kez() -> None:
    olaylar: list[dict[str, object]] = []
    watch = DesktopPermissionWatch(olaylar.append)
    mesaj = izin.MESSAGES["accessibility"]

    watch.handle(ToolExecuted("desktop_click", {}, ToolOutcome.FAILED, mesaj))
    watch.handle(ToolExecuted("desktop_type", {}, ToolOutcome.FAILED, mesaj))
    watch.handle(ToolExecuted("desktop_type", {}, ToolOutcome.FAILED, "başka hata"))
    watch.handle(ToolExecuted("run_shell", {}, ToolOutcome.FAILED, mesaj))
    watch.handle(ToolExecuted("desktop_click", {}, ToolOutcome.OK, mesaj))

    assert olaylar == [
        {
            "olay": "MasaustuIzinGerekli",
            "tur": "accessibility",
            "arac": "desktop_click",
            "ayar_baglantisi": izin.SETTINGS_URLS["accessibility"],
        }
    ]
    watch.handle(TurnFinished())
    watch.handle(
        ToolExecuted(
            "desktop_screenshot", {}, ToolOutcome.FAILED, izin.MESSAGES["screen_recording"]
        )
    )
    assert [o["tur"] for o in olaylar] == ["accessibility", "screen_recording"]

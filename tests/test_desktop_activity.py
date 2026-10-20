"""Küçük önizleme yalnız gerçek, hedefi belli arka plan araçlarından beslenir."""

from fusion_cli.appserver.desktop_activity import DesktopActivity
from fusion_cli.core.events import ToolExecuted, ToolOutcome, ToolStarted, TurnFinished


def test_telefon_veya_genel_ekran_olayi_ajan_onizlemesi_acmaz() -> None:
    activity = DesktopActivity()
    activity.handle(ToolStarted("desktop_screenshot", {}))
    assert activity.view()["active"] is False


def test_hedefli_arac_sonrasi_tur_bitene_kadar_ayni_islem_izlenir() -> None:
    activity = DesktopActivity()
    activity.handle(ToolStarted("desktop_background_inspect", {"window_id": 12, "pid": 34}))
    first = activity.view()
    assert first["active"] is True
    assert first["target"] == {"kind": "window", "id": 12, "pid": 34}
    assert first["activityId"]
    activity.handle(ToolExecuted("desktop_background_inspect", {}, ToolOutcome.OK, "incelendi"))
    assert activity.view()["activityId"] == first["activityId"]
    activity.handle(TurnFinished())
    assert activity.view()["active"] is False


def test_basarisiz_ve_baska_arac_eski_kareyi_tasimaz() -> None:
    activity = DesktopActivity()
    activity.handle(ToolStarted("desktop_background_action", {"window_id": 12, "pid": 34}))
    activity.handle(ToolExecuted("desktop_background_action", {}, ToolOutcome.FAILED, "izin yok"))
    assert activity.view()["active"] is False

"""Fare eylem seti: tık türleri, sürükle, hover, basılı tutma, koordinatlı kaydırma (P-031)."""

from __future__ import annotations

import ctypes
import sys

import pytest

from fusion_cli.core.desktop_frame import DesktopFrame
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop_lock, desktop_mouse
from fusion_cli.tools.desktop_mouse import MouseEvent, mouse_plan


def _izinli(monkeypatch, trusted: bool = True) -> list[tuple[MouseEvent, ...]]:
    monkeypatch.setattr(desktop_mouse, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_mouse, "_framework", lambda: object())
    monkeypatch.setattr(desktop_mouse, "_trusted", lambda loaded: trusted)
    monkeypatch.setattr(desktop_lock, "claim", lambda **_: None)
    planlar: list[tuple[MouseEvent, ...]] = []
    monkeypatch.setattr(desktop_mouse, "_post_mouse", lambda loaded, plan: planlar.append(plan))
    return planlar


def _retina(context: ToolContext) -> None:
    context.desktop.frame = DesktopFrame(1568, 980, 0.0, 0.0, 1440.0, 900.0, 1)


def test_sol_tik_plani_tasima_basma_birakma() -> None:
    plan = mouse_plan("click", (10.0, 20.0))
    assert [(e.kind, e.click_state) for e in plan] == [(5, 0), (1, 1), (2, 1)]


def test_cift_ve_uclu_tik_click_state_artar() -> None:
    assert [e.click_state for e in mouse_plan("double_click", (0, 0))[1:]] == [1, 1, 2, 2]
    assert [e.click_state for e in mouse_plan("triple_click", (0, 0))[1:]] == [1, 1, 2, 2, 3, 3]


def test_sag_ve_orta_tik_dogru_olay_turunu_kullanir() -> None:
    assert [e.kind for e in mouse_plan("right_click", (0, 0))] == [5, 3, 4]
    assert [e.kind for e in mouse_plan("middle_click", (0, 0))] == [5, 25, 26]
    assert all(e.button == 1 for e in mouse_plan("right_click", (0, 0))[1:])


def test_surukleme_ara_noktalarla_gider() -> None:
    plan = mouse_plan("drag", (0.0, 0.0), (60.0, 30.0))

    assert plan[1].kind == 1 and plan[-1].kind == 2 and (plan[-1].x, plan[-1].y) == (60.0, 30.0)
    arada = [e for e in plan if e.kind == 6]
    assert len(arada) == desktop_mouse.DRAG_STEPS and (arada[0].x, arada[0].y) == (10.0, 5.0)
    with pytest.raises(ValueError):
        mouse_plan("drag", (0, 0))


def test_hover_down_up_ve_degistirici_bayraklari() -> None:
    assert [e.kind for e in mouse_plan("hover", (1, 1))] == [5]
    assert [e.kind for e in mouse_plan("down", (1, 1))] == [5, 1]
    assert [e.kind for e in mouse_plan("up", (1, 1))] == [2]
    assert mouse_plan("click", (1, 1), flags=1 << 20)[1].flags == 1 << 20


def test_retina_koordinati_ekran_noktasina_cevrilir(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): desktop_click görüntü pikselini CG noktası sanıyordu (Retina 2x kayma)."""
    planlar = _izinli(monkeypatch)
    context = ToolContext(root=tmp_path)
    _retina(context)

    sonuc = desktop_mouse.desktop_click({"x": 784, "y": 490}, context)

    assert sonuc.ok, sonuc.output
    assert (planlar[0][1].x, planlar[0][1].y) == (720.0, 450.0)


def test_cerceve_yokken_koordinat_nokta_sayilir(tmp_path, monkeypatch) -> None:
    planlar = _izinli(monkeypatch)

    assert desktop_mouse.desktop_mouse(
        {"action": "hover", "x": 5, "y": 6}, ToolContext(root=tmp_path)
    ).ok
    assert (planlar[0][0].x, planlar[0][0].y) == (5.0, 6.0)


def test_goruntu_disi_koordinat_reddedilir(tmp_path, monkeypatch) -> None:
    _izinli(monkeypatch)
    context = ToolContext(root=tmp_path)
    _retina(context)

    sonuc = desktop_mouse.desktop_mouse({"action": "click", "x": 2000, "y": 10}, context)

    assert not sonuc.ok and "1568x980" in sonuc.output


def test_surukleme_araci_hedef_ister_ve_cevirir(tmp_path, monkeypatch) -> None:
    planlar = _izinli(monkeypatch)
    context = ToolContext(root=tmp_path)
    _retina(context)

    assert not desktop_mouse.desktop_mouse({"action": "drag", "x": 1, "y": 1}, context).ok
    sonuc = desktop_mouse.desktop_mouse(
        {"action": "drag", "x": 0, "y": 0, "to_x": 1568, "to_y": 980, "modifiers": "cmd"}, context
    )
    assert sonuc.ok and (planlar[0][-1].x, planlar[0][-1].y) == (1440.0, 900.0)
    assert planlar[0][-1].flags == 1 << 20


def test_gecersiz_girdiler_reddedilir(tmp_path, monkeypatch) -> None:
    _izinli(monkeypatch)
    context = ToolContext(root=tmp_path)

    assert not desktop_mouse.desktop_mouse({"action": "kick", "x": 1, "y": 1}, context).ok
    assert not desktop_mouse.desktop_mouse({"action": "click", "x": True, "y": 1}, context).ok
    assert not desktop_mouse.desktop_mouse({"action": "click", "x": -1, "y": 1}, context).ok
    assert not desktop_mouse.desktop_mouse(
        {"action": "click", "x": 1, "y": 1, "button": "x"}, context
    ).ok
    assert not desktop_mouse.desktop_mouse(
        {"action": "click", "x": 1, "y": 1, "modifiers": "hyper"}, context
    ).ok


def test_izin_yokken_fare_olayi_gonderilmez(tmp_path, monkeypatch) -> None:
    planlar = _izinli(monkeypatch, trusted=False)

    sonuc = desktop_mouse.desktop_click({"x": 50, "y": 40}, ToolContext(root=tmp_path))

    assert not sonuc.ok and "Erişilebilirlik" in sonuc.output and planlar == []
    assert sonuc.structured is not None and sonuc.structured["izin_gerekli"] == "accessibility"


def test_kaydirma_yatay_ve_koordinatli(tmp_path, monkeypatch) -> None:
    planlar = _izinli(monkeypatch)
    kaydirmalar: list[tuple[int, ...]] = []
    monkeypatch.setattr(
        desktop_mouse,
        "_post_scroll",
        lambda loaded, lines, delta_x=0: kaydirmalar.append((lines, delta_x)),
    )
    context = ToolContext(root=tmp_path)
    _retina(context)

    assert desktop_mouse.desktop_scroll({"lines": -3}, context).ok
    sonuc = desktop_mouse.desktop_scroll({"delta_x": 4, "x": 784, "y": 490}, context)

    assert sonuc.ok and "sola" in sonuc.output
    assert kaydirmalar == [(-3, 0), (0, 4)]
    assert planlar == [mouse_plan("hover", (720.0, 450.0))]


def test_kaydirma_sinirlari(tmp_path, monkeypatch) -> None:
    _izinli(monkeypatch)
    context = ToolContext(root=tmp_path)

    assert not desktop_mouse.desktop_scroll({"lines": 101}, context).ok
    assert not desktop_mouse.desktop_scroll({}, context).ok
    assert not desktop_mouse.desktop_scroll({"lines": 1, "x": 3}, context).ok


# --- gerçek ctypes: olay kurulur ama GÖNDERİLMEZ (izin ve odak gerekmez) ---------------- #

_DARWIN = pytest.mark.skipif(sys.platform != "darwin", reason="Quartz yalnız macOS'ta")
#: kCGScrollWheelEventDeltaAxis1 / Axis2 ve kCGMouseEventClickState alan numaraları.
_AXIS_1, _AXIS_2 = 11, 12


def _field(framework: ctypes.CDLL, handle: int, field: int) -> int:
    framework.CGEventGetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    framework.CGEventGetIntegerValueField.restype = ctypes.c_int64
    return int(framework.CGEventGetIntegerValueField(handle, field))


@_DARWIN
@pytest.mark.parametrize(("lines", "delta_x"), [(-4, 0), (5, 3), (0, 7), (100, -100)])
def test_kaydirma_olayi_iki_ekseni_dogru_tasir(lines: int, delta_x: int) -> None:
    """Ölçüldü (31 Ekim, arm64): argtypes'sız variadic çağrıda eksen2 çöp (-27736) geliyordu."""
    framework = desktop_mouse._framework()

    handle = desktop_mouse._create_scroll_event(framework, lines, delta_x)
    try:
        assert (_field(framework, handle, _AXIS_1), _field(framework, handle, _AXIS_2)) == (
            lines,
            delta_x,
        )
    finally:
        framework.CFRelease(handle)


@_DARWIN
def test_fare_olayi_konum_ve_tik_sayisini_tasir() -> None:
    framework = desktop_mouse._framework()
    framework.CGEventGetLocation.argtypes = [ctypes.c_void_p]
    framework.CGEventGetLocation.restype = desktop_mouse._Point
    olay = MouseEvent(1, 720.0, 450.5, 0, 2, 1 << 20)

    handle = desktop_mouse._create_mouse_event(framework, olay)
    try:
        konum = framework.CGEventGetLocation(handle)
        assert (konum.x, konum.y) == (720.0, 450.5)
        assert _field(framework, handle, desktop_mouse._CLICK_STATE_FIELD) == 2
    finally:
        framework.CFRelease(handle)

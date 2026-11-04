"""Pencere inceleme araçları yalnız izinli macOS UI otomasyonuyla çalışır."""

from __future__ import annotations

import subprocess

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop_inspect
from fusion_cli.tools.builtin import build_registry


def test_erisilebilirlik_izni_yokken_sistem_olayi_gonderilmez(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_inspect, "_framework", lambda: object())
    monkeypatch.setattr(desktop_inspect, "_trusted", lambda framework: False)
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(desktop_inspect.subprocess, "run", fake_run)

    result = desktop_inspect.desktop_windows({}, ToolContext(root=tmp_path))

    assert not result.ok and "Erişilebilirlik" in result.output
    assert not calls


def test_pencere_adi_kabuga_girmeden_ayri_arguman_olur(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_inspect, "_framework", lambda: object())
    monkeypatch.setattr(desktop_inspect, "_trusted", lambda framework: True)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, f"TextEdit\t42\t{name}\t0\t0\t100\t100", "")

    monkeypatch.setattr(desktop_inspect.subprocess, "run", fake_run)
    name = "Pencere; $(touch /tmp/yan-etki)"
    _fake_focus_probe(monkeypatch, name, [0.0, 0.0, 100.0, 100.0])
    result = desktop_inspect.desktop_window_focus(
        {"app": "TextEdit", "window": name}, ToolContext(root=tmp_path)
    )

    assert result.ok
    assert calls[0][-2:] == ["TextEdit", name]
    assert {"desktop_windows", "desktop_window_focus", "desktop_accessibility"} <= set(
        build_registry().names()
    )


# --- Dalga 4 (T1-44) -----------------------------------------------------------------


def _fake_run_factory(stdout="", returncode=0, hata=None):
    import subprocess

    def _run(command, **kwargs):
        if hata is not None:
            raise hata
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    return _run


def test_cikti_kirpilirsa_not_eklenir(monkeypatch):
    from fusion_cli.tools import desktop_inspect

    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_inspect, "_framework", lambda: object())
    monkeypatch.setattr(desktop_inspect, "_trusted", lambda f: True)
    monkeypatch.setattr(desktop_inspect.subprocess, "run", _fake_run_factory("x" * 15_000))

    sonuc = desktop_inspect._run("script")

    assert sonuc.ok and "KIRPILDI" in sonuc.output and "desktop_background_inspect" in sonuc.output


def test_zaman_asimi_yonlendirici_mesaj_verir(monkeypatch):
    import subprocess

    from fusion_cli.tools import desktop_inspect

    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_inspect, "_framework", lambda: object())
    monkeypatch.setattr(desktop_inspect, "_trusted", lambda f: True)
    monkeypatch.setattr(
        desktop_inspect.subprocess,
        "run",
        _fake_run_factory(hata=subprocess.TimeoutExpired("osascript", 15)),
    )

    sonuc = desktop_inspect._run("script")

    assert not sonuc.ok and "desktop_background_inspect" in sonuc.output


def test_pencere_null_kabul_edilir(monkeypatch):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import desktop_inspect

    monkeypatch.setattr(
        desktop_inspect,
        "_run",
        lambda *a: desktop_inspect.ToolResult("Safari\t42\tPage\t0\t0\t100\t100"),
    )

    _fake_focus_probe(monkeypatch, "Page", [0.0, 0.0, 100.0, 100.0])
    sonuc = desktop_inspect.desktop_window_focus(
        {"app": "Safari", "window": None}, ToolContext(root=".")
    )

    assert sonuc.ok


def test_focus_requires_observed_identity_and_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_inspect, "_run", lambda *a: desktop_inspect.ToolResult("ok"))
    context = ToolContext(root=tmp_path)
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert not result.ok


def test_focus_binds_verified_window_and_requires_new_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(
        desktop_inspect,
        "_run",
        lambda *a: desktop_inspect.ToolResult("Calculator\t42\tCalculator\t350\t260\t210\t380"),
    )
    context = ToolContext(root=tmp_path)
    _fake_focus_probe(monkeypatch, "Calculator", [350.0, 260.0, 210.0, 380.0])
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert result.ok
    assert context.desktop.focused_window_id == 101
    assert context.desktop.focused_window_title == "Calculator"
    assert context.desktop.focused_window == (42, 350.0, 260.0, 210.0, 380.0)
    assert context.desktop.frame is None


def test_failed_focus_invalidates_old_screenshot_before_any_click(tmp_path, monkeypatch):
    from fusion_cli.core.desktop_frame import DesktopFrame
    from fusion_cli.tools.desktop_mouse import _to_point

    context = ToolContext(root=tmp_path)
    context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    context.desktop.focused_window = (42, 350.0, 260.0, 210.0, 380.0)
    monkeypatch.setattr(
        desktop_inspect, "_run", lambda *args: desktop_inspect.ToolResult.failure("focus failed")
    )
    result = desktop_inspect.desktop_window_focus({"app": "Notes"}, context)
    assert not result.ok
    assert isinstance(_to_point(context, (400, 300)), str)
    assert context.desktop.frame is None


def _fake_focus_probe(monkeypatch, title, bounds):
    monkeypatch.setattr(
        desktop_inspect,
        "invoke_sync",
        lambda *args: {
            "ok": True,
            "pid": 42,
            "window": {"id": 101, "title": title, "bounds": bounds},
        },
    )


async def test_failed_focus_cannot_be_reenabled_by_unbound_screenshot(tmp_path, monkeypatch):
    from fusion_cli.core.desktop_frame import DesktopFrame
    from fusion_cli.tools.desktop_mouse import _to_point
    from fusion_cli.tools.desktop_policy import assess

    context = ToolContext(root=tmp_path)
    monkeypatch.setattr(
        desktop_inspect, "_run", lambda *args: desktop_inspect.ToolResult.failure("focus failed")
    )
    assert not desktop_inspect.desktop_window_focus({"app": "Notes"}, context).ok
    context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    assert isinstance(_to_point(context, (400, 300)), str)

    async def probe(request):
        return {"ok": True, "app": "Notes", "pid": 42}

    assessment = await assess("desktop_click", {"x": 400, "y": 300}, context, probe)
    assert assessment is not None and assessment.blocked


async def test_failed_or_malformed_focus_blocks_event_until_valid_refocus_and_frame(
    tmp_path,
    monkeypatch,
):
    from fusion_cli.core.desktop_frame import DesktopFrame
    from fusion_cli.tools import desktop_mouse
    from tests.test_desktop_mouse import _izinli

    plans = _izinli(monkeypatch)
    context = ToolContext(root=tmp_path)
    for response in (
        desktop_inspect.ToolResult.failure("native failure"),
        desktop_inspect.ToolResult("malformed observation"),
    ):
        context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
        monkeypatch.setattr(desktop_inspect, "_run", lambda *a, response=response: response)
        assert not desktop_inspect.desktop_window_focus({"app": "Calculator"}, context).ok
        assert not desktop_mouse.desktop_click({"x": 400, "y": 300}, context).ok
        context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
        assert not desktop_mouse.desktop_click({"x": 400, "y": 300}, context).ok
    assert not plans

    monkeypatch.setattr(
        desktop_inspect,
        "_run",
        lambda *a: desktop_inspect.ToolResult("Calculator\t42\tCalculator\t350\t260\t210\t380"),
    )
    _fake_focus_probe(monkeypatch, "Calculator", [350.0, 260.0, 210.0, 380.0])
    assert desktop_inspect.desktop_window_focus({"app": "Calculator"}, context).ok
    assert not desktop_mouse.desktop_click({"x": 400, "y": 300}, context).ok
    assert not plans
    context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    assert desktop_mouse.desktop_click({"x": 400, "y": 300}, context).ok
    assert len(plans) == 1

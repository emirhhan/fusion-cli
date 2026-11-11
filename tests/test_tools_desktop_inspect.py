"""Pencere inceleme araçları yalnız izinli macOS UI otomasyonuyla çalışır."""

from __future__ import annotations

import subprocess

import pytest

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
        lambda *a, **kwargs: desktop_inspect.ToolResult("Safari\t42\tPage\t0\t0\t100\t100"),
    )

    _fake_focus_probe(monkeypatch, "Page", [0.0, 0.0, 100.0, 100.0])
    sonuc = desktop_inspect.desktop_window_focus(
        {"app": "Safari", "window": None}, ToolContext(root=".")
    )

    assert sonuc.ok


def test_focus_requires_observed_identity_and_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr(
        desktop_inspect, "_run", lambda *a, **kwargs: desktop_inspect.ToolResult("ok")
    )
    context = ToolContext(root=tmp_path)
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert not result.ok


def test_focus_binds_verified_window_and_requires_new_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(
        desktop_inspect,
        "_run",
        lambda *a, **kwargs: desktop_inspect.ToolResult(
            "Calculator\t42\tCalculator\t350\t260\t210\t380"
        ),
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
        desktop_inspect,
        "_run",
        lambda *args, **kwargs: desktop_inspect.ToolResult.failure("focus failed"),
    )
    result = desktop_inspect.desktop_window_focus({"app": "Notes"}, context)
    assert not result.ok
    assert isinstance(_to_point(context, (400, 300)), str)
    assert context.desktop.frame is None


def _fake_focus_probe(monkeypatch, title, bounds):
    monkeypatch.setattr(
        desktop_inspect,
        "invoke_sync",
        lambda *args, **kwargs: {
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
        desktop_inspect,
        "_run",
        lambda *args, **kwargs: desktop_inspect.ToolResult.failure("focus failed"),
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
        monkeypatch.setattr(
            desktop_inspect, "_run", lambda *a, response=response, **kwargs: response
        )
        assert not desktop_inspect.desktop_window_focus({"app": "Calculator"}, context).ok
        assert not desktop_mouse.desktop_click({"x": 400, "y": 300}, context).ok
        context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
        assert not desktop_mouse.desktop_click({"x": 400, "y": 300}, context).ok
    assert not plans

    monkeypatch.setattr(
        desktop_inspect,
        "_run",
        lambda *a, **kwargs: desktop_inspect.ToolResult(
            "Calculator\t42\tCalculator\t350\t260\t210\t380"
        ),
    )
    _fake_focus_probe(monkeypatch, "Calculator", [350.0, 260.0, 210.0, 380.0])
    assert desktop_inspect.desktop_window_focus({"app": "Calculator"}, context).ok
    assert not desktop_mouse.desktop_click({"x": 400, "y": 300}, context).ok
    assert not plans
    context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    assert desktop_mouse.desktop_click({"x": 400, "y": 300}, context).ok
    assert len(plans) == 1


async def test_focus_exposes_verified_identity_consumable_by_background_inspect(
    tmp_path, monkeypatch
):
    from fusion_cli.tools import desktop_background

    context = ToolContext(root=tmp_path)
    monkeypatch.setattr(
        desktop_inspect,
        "_run",
        lambda *a, **kwargs: desktop_inspect.ToolResult(
            "Calculator\t42\tCalculator\t350\t260\t210\t380"
        ),
    )
    _fake_focus_probe(monkeypatch, "Calculator", [350.0, 260.0, 210.0, 380.0])
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert result.ok
    assert result.output == (
        "Öne getirildi ve doğrulandı: Calculator — Calculator; window_id=101, pid=42, "
        "sınırlar=(350,260,210,380) ekran noktası. "
        "İşlemden önce bu window_id ve pid ile desktop_background_inspect çağır; "
        "pencerenin güncel durumunu ve varsa display.value değerini oku. "
        "Kullanıcının yöntem sınırlarına uy. "
        "Adı belli düğmenin güncel ve tekil ref'i varsa aynı window_id, pid ve ref ile "
        "desktop_background_action (action=press) kullan. "
        "Sonucu aynı pencereyi yeniden inceleyerek doğrula. "
        "Koordinat gerekiyorsa ve kullanıcı izin veriyorsa yeni tam desktop_screenshot al; "
        "hedefin koordinatını görüntü modele ulaştıktan sonraki adımda seç."
    )
    assert result.structured is not None
    target = result.structured["target"]
    assert target == {"window_id": 101, "pid": 42}
    calls = []

    async def invoke(self, operation, arguments):
        calls.append((operation, arguments))
        return {"ok": True, "elements": []}

    monkeypatch.setattr(desktop_background.SwiftDesktop, "invoke", invoke)
    inspection = await desktop_background.desktop_background_inspect(target, context)
    assert inspection.ok and calls == [("inspect", {"kind": "window", "id": 101, "pid": 42})]


async def test_focus_waits_for_actual_foreground_pid_and_then_native_identity(
    tmp_path, monkeypatch
):
    target = "Calculator\t42\tCalculator\t350\t260\t210\t380"
    other = "Other App\t99\tOther\t0\t0\t100\t100"
    observations = []

    def run(script, *args, **kwargs):
        if script == desktop_inspect.FOCUS_SCRIPT:
            return desktop_inspect.ToolResult(target)
        observations.append(script)
        return desktop_inspect.ToolResult(other if len(observations) == 1 else target)

    monkeypatch.setattr(desktop_inspect, "_run", run)
    clock = [0.0]
    import time

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    def native(*args):
        return {
            "ok": True,
            "pid": 42 if len(observations) == 2 else 99,
            "window": {"id": 101, "title": "Calculator", "bounds": [350.0, 260.0, 210.0, 380.0]},
        }

    monkeypatch.setattr(desktop_inspect, "invoke_sync", native)
    context = ToolContext(root=tmp_path)
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert result.ok and len(observations) == 2
    assert context.desktop.focused_window_id == 101


async def test_focus_settle_timeout_keeps_refocus_lock_and_never_claims_success(
    tmp_path, monkeypatch
):
    target = "Calculator\t42\tCalculator\t350\t260\t210\t380"
    other = "Other App\t99\tOther\t0\t0\t100\t100"

    def run(script, *args, **kwargs):
        return desktop_inspect.ToolResult(
            target if script == desktop_inspect.FOCUS_SCRIPT else other
        )

    monkeypatch.setattr(desktop_inspect, "_run", run)
    clock = [0.0]
    import time

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    native_calls = []

    def native(*args):
        native_calls.append(args)
        return {"ok": False}

    monkeypatch.setattr(desktop_inspect, "invoke_sync", native)
    context = ToolContext(root=tmp_path)
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert not result.ok and context.desktop.focus_required and context.desktop.frame is None
    assert len(native_calls) == 1
    assert native_calls[0][1]["request"]["pid"] == 42
    assert "window_diagnostics" in native_calls[0][1]["request"]
    assert 0 < clock[0] <= 3


def test_focus_uses_actual_pid_instead_of_localized_requested_name(tmp_path, monkeypatch):
    target = "Calculator\t42\tCalculator\t350\t260\t210\t380"
    monkeypatch.setattr(desktop_inspect, "_run", lambda *a, **k: desktop_inspect.ToolResult(target))
    _fake_focus_probe(monkeypatch, "Calculator", [350.0, 260.0, 210.0, 380.0])
    context = ToolContext(root=tmp_path)
    result = desktop_inspect.desktop_window_focus({"app": "Hesap Makinesi"}, context)
    assert result.ok and context.desktop.focused_window_id == 101


def test_native_focus_mismatch_reports_only_boolean_checks_and_stays_locked(tmp_path, monkeypatch):
    target = "Calculator\t42\tCalculator\t350\t260\t210\t380"
    monkeypatch.setattr(desktop_inspect, "_run", lambda *a, **k: desktop_inspect.ToolResult(target))
    monkeypatch.setattr(
        desktop_inspect,
        "invoke_sync",
        lambda *a: {
            "ok": True,
            "pid": 42,
            "window": {
                "id": 101,
                "title": "Unexpected private title",
                "bounds": [350.0, 260.0, 210.0, 380.0],
            },
        },
    )
    context = ToolContext(root=tmp_path)
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert not result.ok and context.desktop.focus_required
    assert result.structured is not None
    assert result.structured["focus_validation"] == {
        "native_ok": True,
        "pid_matches": True,
        "window_known": True,
        "title_matches": False,
        "bounds_match": True,
    }
    assert "Unexpected private title" not in result.output


def test_named_focus_waits_through_same_pid_wrong_window_before_native_validation(
    tmp_path, monkeypatch
):
    target = "Calculator\t42\tHesap Makinesi\t350\t260\t230\t408"
    overlay = "Calculator\t42\tWindow\t350\t260\t30\t30"
    seen = []

    def run(script, *args, **kwargs):
        if script == desktop_inspect.FOCUS_SCRIPT:
            return desktop_inspect.ToolResult(target)
        seen.append(script)
        return desktop_inspect.ToolResult(overlay if len(seen) == 1 else target)

    monkeypatch.setattr(desktop_inspect, "_run", run)
    clock = [0.0]
    import time

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    _fake_focus_probe(monkeypatch, "Hesap Makinesi", [350.0, 260.0, 230.0, 408.0])
    context = ToolContext(root=tmp_path)
    result = desktop_inspect.desktop_window_focus(
        {"app": "Calculator", "window": "Hesap Makinesi"}, context
    )
    assert result.ok and len(seen) == 2 and context.desktop.focused_window_title == "Hesap Makinesi"


@pytest.mark.parametrize("named", [False, True])
def test_focused_attribute_selects_main_when_unfocused_overlay_is_first(
    tmp_path, monkeypatch, named
):
    main = "Calculator\t42\tHesap Makinesi\t350\t260\t230\t408"
    overlay = "Calculator\t42\tWindow\t350\t260\t30\t30"

    # Distinct API semantics: AXWindows[0] is overlay, AXFocusedWindow is main.
    def run(script, *args, **kwargs):
        if script == desktop_inspect.FOCUS_SCRIPT:
            uses_focused = 'set selectedWindow to value of attribute "AXFocusedWindow"' in script
            return desktop_inspect.ToolResult(main if named or uses_focused else overlay)
        uses_focused = 'set frontWindow to value of attribute "AXFocusedWindow"' in script
        return desktop_inspect.ToolResult(main if uses_focused else overlay)

    monkeypatch.setattr(desktop_inspect, "_run", run)
    clock = [0.0]
    import time

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    _fake_focus_probe(monkeypatch, "Hesap Makinesi", [350.0, 260.0, 230.0, 408.0])
    context = ToolContext(root=tmp_path)
    args = {"app": "Calculator", **({"window": "Hesap Makinesi"} if named else {})}
    result = desktop_inspect.desktop_window_focus(args, context)
    assert result.ok and context.desktop.focused_window_title == "Hesap Makinesi"
    assert context.desktop.focused_window_id == 101


def test_settle_failure_reports_other_foreground_pid_as_boolean_only(tmp_path, monkeypatch):
    target = "Calculator\t42\tHesap Makinesi\t350\t260\t230\t408"
    other = "Private other application\t99\tHesap Makinesi\t350\t260\t230\t408"

    def run(script, *args, **kwargs):
        return desktop_inspect.ToolResult(
            target if script == desktop_inspect.FOCUS_SCRIPT else other
        )

    monkeypatch.setattr(desktop_inspect, "_run", run)
    clock = [0.0]
    import time

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(
        desktop_inspect,
        "invoke_sync",
        lambda *a: {"ok": True, "window_diagnostics": {"ax_trusted": True, "windows_count": 2}},
    )
    context = ToolContext(root=tmp_path)
    result = desktop_inspect.desktop_window_focus(
        {"app": "Calculator", "window": "Hesap Makinesi"}, context
    )
    assert not result.ok and context.desktop.focus_required and context.desktop.frame is None
    assert result.structured is not None
    assert result.structured["focus_settle"] == {
        "observation_ok": True,
        "focused_window_known": True,
        "pid_matches": False,
        "title_matches": True,
    }
    assert "Private other application" not in str(result.structured) + result.output


@pytest.mark.parametrize("phase", ["activation", "poll"])
def test_unavailable_focused_attribute_never_falls_back_to_front_order(
    tmp_path,
    monkeypatch,
    phase,
):
    from fusion_cli.core.desktop_frame import DesktopFrame

    target = "Calculator\t42\tHesap Makinesi\t350\t260\t230\t408"

    def run(script, *args, **kwargs):
        if script == desktop_inspect.FOCUS_SCRIPT:
            assert 'set selectedWindow to value of attribute "AXFocusedWindow"' in script
            assert "set selectedWindow to front window" not in script
            if phase == "activation":
                return desktop_inspect.ToolResult.failure("AXFocusedWindow unavailable")
            return desktop_inspect.ToolResult(target)
        assert 'set frontWindow to value of attribute "AXFocusedWindow"' in script
        assert "set frontWindow to front window" not in script
        return desktop_inspect.ToolResult.failure("AXFocusedWindow unavailable")

    monkeypatch.setattr(desktop_inspect, "_run", run)
    clock = [0.0]
    import time

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    native_calls = []

    def native(operation, target):
        native_calls.append(target)
        assert target["request"].get("pid") == 42  # own-target diagnostic only
        return {"ok": True, "window_diagnostics": {}}

    monkeypatch.setattr(desktop_inspect, "invoke_sync", native)
    context = ToolContext(root=tmp_path)
    context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert not result.ok and context.desktop.focus_required and context.desktop.frame is None
    assert context.desktop.focused_window is None
    if phase == "poll":
        assert result.structured is not None
        assert result.structured["focus_settle"] == {
            "observation_ok": False,
            "focused_window_known": False,
        }
        assert len(native_calls) == 1
    else:
        assert native_calls == []


@pytest.mark.parametrize("named", [False, True])
def test_activation_capture_waits_for_delayed_focused_attribute(tmp_path, monkeypatch, named):
    """The OS may acknowledge frontmost before exposing AXFocusedWindow."""
    target = "Calculator\t42\tHesap Makinesi\t350\t260\t230\t408"
    observed_attributes = []

    def run(command, **kwargs):
        script = command[2]
        if script == desktop_inspect.FOCUS_SCRIPT:
            assert command[-2:] == ["Calculator", "Hesap Makinesi" if named else ""]
            if not named:
                # Script contract: nil first, real focused window on the second read.
                focused = iter([None, target])
                retries = 40 if "repeat with focusAttempt from 1 to 40" in script else 1
                for _ in range(retries):
                    value = next(focused)
                    observed_attributes.append(value is not None)
                    if value is not None:
                        break
                else:
                    return subprocess.CompletedProcess(
                        command, 1, "", "Actual focused window is unavailable"
                    )
        return subprocess.CompletedProcess(command, 0, target, "")

    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_inspect, "_framework", lambda: object())
    monkeypatch.setattr(desktop_inspect, "_trusted", lambda framework: True)
    monkeypatch.setattr(desktop_inspect.subprocess, "run", run)
    _fake_focus_probe(monkeypatch, "Hesap Makinesi", [350.0, 260.0, 230.0, 408.0])
    context = ToolContext(root=tmp_path)
    args = {"app": "Calculator", **({"window": "Hesap Makinesi"} if named else {})}
    result = desktop_inspect.desktop_window_focus(args, context)
    assert result.ok and context.desktop.focused_window_id == 101
    assert observed_attributes == ([] if named else [False, True])


def test_activation_missing_focus_has_bounded_reads_and_never_uses_stale_frame(
    tmp_path, monkeypatch
):
    from fusion_cli.core.desktop_frame import DesktopFrame

    activation_reads = []

    def run(command, **kwargs):
        script = command[2]
        assert script == desktop_inspect.FOCUS_SCRIPT
        assert "repeat with focusAttempt from 1 to 40" in script
        assert "delay 0.05" in script
        assert 'set selectedWindow to value of attribute "AXFocusedWindow"' in script
        assert "set selectedWindow to front window" not in script
        assert 'attribute "AXMainWindow"' not in script
        activation_reads.extend([None] * 40)
        return subprocess.CompletedProcess(command, 1, "", "Actual focused window is unavailable")

    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_inspect, "_framework", lambda: object())
    monkeypatch.setattr(desktop_inspect, "_trusted", lambda framework: True)
    monkeypatch.setattr(desktop_inspect.subprocess, "run", run)
    monkeypatch.setattr(
        desktop_inspect, "invoke_sync", lambda *args: pytest.fail("native validation must not run")
    )
    context = ToolContext(root=tmp_path)
    context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert not result.ok and len(activation_reads) == 40
    assert context.desktop.focus_required and context.desktop.frame is None
    assert context.desktop.focused_window_id == 0


def test_activation_capture_does_not_switch_to_restarted_process(tmp_path, monkeypatch):
    changed = "Calculator\t43\tHesap Makinesi\t350\t260\t230\t408"

    def run(command, **kwargs):
        script = command[2]
        if (
            script == desktop_inspect.FOCUS_SCRIPT
            and "set targetPID to unix id of targetProcess" in script
        ):
            assert "if (unix id of targetProcess) is not targetPID then" in script
            return subprocess.CompletedProcess(command, 1, "", "Target application process changed")
        return subprocess.CompletedProcess(command, 0, changed, "")

    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_inspect, "_framework", lambda: object())
    monkeypatch.setattr(desktop_inspect, "_trusted", lambda framework: True)
    monkeypatch.setattr(desktop_inspect.subprocess, "run", run)
    monkeypatch.setattr(
        desktop_inspect,
        "invoke_sync",
        lambda *args: {
            "ok": True,
            "pid": 43,
            "window": {
                "id": 101,
                "title": "Hesap Makinesi",
                "bounds": [350.0, 260.0, 230.0, 408.0],
            },
        },
    )
    context = ToolContext(root=tmp_path)
    result = desktop_inspect.desktop_window_focus({"app": "Calculator"}, context)
    assert not result.ok and context.desktop.focus_required
    assert context.desktop.focused_window is None

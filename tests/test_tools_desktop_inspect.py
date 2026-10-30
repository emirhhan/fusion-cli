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
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(desktop_inspect.subprocess, "run", fake_run)
    name = "Pencere; $(touch /tmp/yan-etki)"
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

    monkeypatch.setattr(desktop_inspect, "_run", lambda *a: desktop_inspect.ToolResult("ok"))

    sonuc = desktop_inspect.desktop_window_focus(
        {"app": "Safari", "window": None}, ToolContext(root=".")
    )

    assert sonuc.ok

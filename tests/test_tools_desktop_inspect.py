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

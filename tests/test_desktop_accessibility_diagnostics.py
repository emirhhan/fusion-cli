"""Boş yerel erişilebilirlik çıktısı kontrol kanıtı gibi sunulmaz."""

from __future__ import annotations

import subprocess

import pytest

from fusion_cli.core.desktop_settings import DesktopSettings
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop_inspect

# Ölçülen Calculator çıktısı; hem boş dolaşım hem tüm satırların serileştirme
# hatası aynı yakalamayı üretebilir. Bu iki neden çıktıdan ayırt edilemez.
_BARE_CALCULATOR = "Uygulama: Calculator\nPaket: com.apple.calculator\nPencere: HesapMakinesi\n"


@pytest.fixture
def native_capture(monkeypatch):
    """Yalnız yerel süreç sınırını değiştir; üretim sonuç biçimleyicisi çalışsın."""
    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_inspect, "_framework", lambda: object())
    monkeypatch.setattr(desktop_inspect, "_trusted", lambda framework: True)

    def capture(stdout, *, returncode=0, stderr=""):
        def run(command, **kwargs):
            return subprocess.CompletedProcess(command, returncode, stdout, stderr)

        monkeypatch.setattr(desktop_inspect.subprocess, "run", run)

    return capture


@pytest.mark.parametrize(
    "stdout",
    [
        pytest.param(_BARE_CALCULATOR, id="observed-headers-empty-or-failed-serialization"),
        pytest.param("Uygulama: Calculator\nPencere: HesapMakinesi\n", id="no-bundle"),
        pytest.param("Uygulama: Calculator\nPencere: \n", id="unnamed-window"),
        pytest.param("", id="empty-successful-capture"),
    ],
)
def test_accessibility_without_controls_reports_missing_evidence(tmp_path, native_capture, stdout):
    native_capture(stdout)

    result = desktop_inspect.desktop_accessibility({}, ToolContext(root=tmp_path))

    assert result.ok  # Süreç başarısı/başarısızlığı sözleşmesi değişmez.
    assert result.output.startswith(stdout.strip() or "Öğe bulunamadı.")
    assert "Kontrol ağacı alınamadı" in result.output
    assert "eylem ref'i yok" in result.output
    assert "düğme koordinatı ya da eylem yetkisi çıkarılamaz" in result.output
    assert "Neden bu sonuçtan belirlenemez" in result.output
    assert result.structured is None


@pytest.mark.parametrize(
    "rows",
    ["AXButton\t7\t10,20,30,40 ekran noktası\n", "AXGroup\t\n", "AXButton\tPencere: A\n"],
)
def test_accessibility_with_serialized_controls_is_unchanged(tmp_path, native_capture, rows):
    stdout = _BARE_CALCULATOR + rows
    native_capture(stdout)

    result = desktop_inspect.desktop_accessibility({}, ToolContext(root=tmp_path))

    assert result.ok
    assert result.output == stdout.strip()
    assert result.structured is None


@pytest.mark.parametrize(
    "stdout",
    [
        "Uygulama: Calculator\nAXButton\tPencere: HesapMakinesi\n",
        "Uygulama: Calculator\nPaket: com.apple.calculator\nAXButton\tPencere: A\n",
        "unrecognized native output",
    ],
)
def test_non_metadata_output_is_not_reclassified(tmp_path, native_capture, stdout):
    native_capture(stdout)

    result = desktop_inspect.desktop_accessibility({}, ToolContext(root=tmp_path))

    assert result.ok
    assert result.output == stdout.strip()


def test_windowless_native_failure_keeps_original_error(tmp_path, native_capture):
    native_capture("", returncode=1, stderr="System Events: front window unavailable\n")

    result = desktop_inspect.desktop_accessibility({}, ToolContext(root=tmp_path))

    assert not result.ok
    assert result.output == "Pencere erişimi başarısız: System Events: front window unavailable"


def test_metadata_only_denied_app_is_still_redacted(tmp_path, native_capture):
    native_capture(_BARE_CALCULATOR)
    context = ToolContext(
        root=tmp_path, desktop_settings=DesktopSettings(denied_apps=("Calculator",))
    )

    result = desktop_inspect.desktop_accessibility({}, context)

    assert not result.ok
    assert result.output == desktop_inspect.HIDDEN_FRONT_MESSAGE.format(app="Calculator")
    assert "HesapMakinesi" not in result.output
    assert "com.apple.calculator" not in result.output


def test_unsupported_platform_keeps_original_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_inspect, "_mac_only", lambda: "platform unavailable")

    result = desktop_inspect.desktop_accessibility({}, ToolContext(root=tmp_path))

    assert not result.ok
    assert result.output == "platform unavailable"

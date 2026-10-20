from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from desktop_build.runtime import native_helper
from pytest import MonkeyPatch

from fusion_cli.tools import native_desktop


async def test_paketli_yardimci_swift_derlemeden_kullanilir(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / native_desktop.BUNDLED_HELPER_NAME
    await asyncio.to_thread(binary.write_bytes, b"paketli-yardimci")
    binary.chmod(0o755)
    monkeypatch.setattr(native_desktop, "_data_directory", lambda: tmp_path)
    process = AsyncMock(side_effect=AssertionError("Derleyici çağrılmamalı."))
    monkeypatch.setattr(native_desktop, "_process", process)
    assert await native_desktop._executable() == binary
    process.assert_not_called()


@pytest.mark.parametrize("invalid", ["symlink", "directory", "not_executable", "writable"])
async def test_gecersiz_paketli_yardimci_gelistirme_derlemesine_dusmez(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    invalid: str,
) -> None:
    binary = tmp_path / native_desktop.BUNDLED_HELPER_NAME
    if invalid == "symlink":
        binary.symlink_to(tmp_path / "bulunmayan-hedef")
    elif invalid == "directory":
        binary.mkdir()
    else:
        await asyncio.to_thread(binary.write_bytes, b"gecersiz-yardimci")
        binary.chmod(0o644 if invalid == "not_executable" else 0o777)
    monkeypatch.setattr(native_desktop, "_data_directory", lambda: tmp_path)
    process = AsyncMock()
    monkeypatch.setattr(native_desktop, "_process", process)
    with pytest.raises(OSError):
        await native_desktop._executable()
    process.assert_not_called()


async def test_paketli_uygulamada_eksik_yardimci_swift_istemez(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(native_desktop, "_data_directory", lambda: tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(OSError, match="eksik"):
        await native_desktop._executable()


def test_derleme_yardimciyi_ayni_swift_kaynagindan_uretir(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    calls: list[list[str]] = []

    def run(arguments: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        assert options["timeout"] == native_helper.HELPER_BUILD_TIMEOUT_S
        assert options["check"] is True
        Path(arguments[-1]).write_bytes(b"derlenmis-yardimci")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    result = native_helper.build_native_helper(str(tmp_path), str(tmp_path / "build"))
    assert result is not None
    assert calls == [
        [
            "/usr/bin/swiftc",
            str(tmp_path / "src/fusion_cli/tools/data/desktop_host.swift"),
            "-o",
            result,
        ]
    ]
    assert Path(result).name == native_desktop.BUNDLED_HELPER_NAME
    assert Path(result).stat().st_mode & 0o777 == 0o755


def test_windows_derlemesi_macos_yardimcisi_uretmez(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert native_helper.build_native_helper(str(tmp_path), str(tmp_path / "build")) is None
    assert not (tmp_path / "build").exists()


def test_pyinstaller_tarifi_yardimciyi_resmi_workpath_ile_paketler(tmp_path: Path) -> None:
    """Tarif bağlantısı PyInstaller'ın gerçek küçük harfli global adını kullanır."""
    import ast

    source = Path(__file__).parents[1] / "desktop_build/runtime/fusion_runtime.spec"
    tree = ast.parse(source.read_text())
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_native_helper"
            for target in node.targets
        )
    )
    calls: list[tuple[str, str]] = []

    def build(root: str, work_directory: str) -> str:
        calls.append((root, work_directory))
        return str(tmp_path / "fusion-desktop-host")

    namespace = {
        "_native_build": {"build_native_helper": build},
        "_repo_root": "/kaynak",
        "workpath": str(tmp_path),
    }
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(source), "exec"), namespace)
    assert calls == [("/kaynak", str(tmp_path))]
    assert namespace["_native_helper"] == str(tmp_path / "fusion-desktop-host")

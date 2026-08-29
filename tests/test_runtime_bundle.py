from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from desktop_build.runtime import build_runtime as runtime_builder
from desktop_build.runtime.build_runtime import (
    build_manifest,
    build_runtime,
    macos_target,
    write_archive,
)


def test_macos_target_mimariyi_tauri_adina_cevirir():
    assert macos_target("arm64") == "aarch64-apple-darwin"
    assert macos_target("x86_64") == "x86_64-apple-darwin"


def test_manifest_dosyalari_sirali_ve_ozetlidir(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    executable = root / "fusion"
    executable.write_bytes(b"runtime")
    executable.chmod(0o755)
    (root / "z.txt").write_text("z", encoding="utf-8")
    archive = tmp_path / "fusion-runtime.tar.gz"
    write_archive(root, archive)

    manifest = build_manifest(root, archive, version="0.3.0a1", target="aarch64-apple-darwin")

    assert manifest["entrypoint"] == "fusion"
    assert [item["path"] for item in manifest["files"]] == ["fusion", "z.txt"]
    assert manifest["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_ayni_girdi_ayni_arsivi_uretir(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "fusion").write_bytes(b"same")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    write_archive(root, first)
    write_archive(root, second)

    assert first.read_bytes() == second.read_bytes()


def test_manifest_symlink_girdisini_hedefiyle_isaretler(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "fusion").write_bytes(b"runtime")
    (root / "libfusion.dylib").write_bytes(b"lib")
    link = root / "libfusion.so"
    link.symlink_to("libfusion.dylib")
    archive = tmp_path / "fusion-runtime.tar.gz"
    write_archive(root, archive)

    manifest = build_manifest(root, archive, version="0.3.0a1", target="aarch64-apple-darwin")

    entry = next(item for item in manifest["files"] if item["path"] == "libfusion.so")
    assert entry["kind"] == "symlink"
    assert entry["target"] == "libfusion.dylib"


def test_runtime_derlemesi_izlenen_readme_dosyasini_korur(tmp_path: Path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    readme = output / "README.md"
    readme.write_text("Bu dosya depoya aittir.\n", encoding="utf-8")

    def fake_pyinstaller(dist_path: Path, _build_path: Path) -> None:
        bundle = dist_path / "fusion-runtime"
        bundle.mkdir(parents=True)
        executable = bundle / "fusion"
        executable.write_bytes(b"runtime")
        executable.chmod(0o755)

    monkeypatch.setattr(runtime_builder, "_run_pyinstaller", fake_pyinstaller)

    build_runtime(output, tmp_path / "work")

    assert readme.read_text(encoding="utf-8") == "Bu dosya depoya aittir.\n"


def test_windows_hedefi_ve_exe_giris_noktasi():
    """Windows paketi Tauri'nin MSVC üçlüsünü ve `.exe` giriş noktasını taşımalı.

    PyInstaller çapraz derleme yapmaz: Windows ikilisi Windows'ta üretilir. Ama
    hedef adı ve giriş noktası ADI platformdan türetilir; bu iki alanı yanlış
    yazmak, Rust tarafındaki `RuntimeManifest::validate` ve giriş noktası
    çözümlemesini paket açıldıktan SONRA patlatır.
    """
    from desktop_build.runtime.build_runtime import entrypoint_name, platform_target

    assert platform_target("Darwin", "arm64") == "aarch64-apple-darwin"
    assert platform_target("Darwin", "x86_64") == "x86_64-apple-darwin"
    assert platform_target("Windows", "AMD64") == "x86_64-pc-windows-msvc"
    assert platform_target("Windows", "ARM64") == "aarch64-pc-windows-msvc"

    assert entrypoint_name("Darwin") == "fusion"
    assert entrypoint_name("Windows") == "fusion.exe"


def test_desteklenmeyen_platform_sessizce_gecilmez():
    from desktop_build.runtime.build_runtime import platform_target

    with pytest.raises(ValueError):
        platform_target("Linux", "x86_64")
    with pytest.raises(ValueError):
        platform_target("Windows", "itanium")

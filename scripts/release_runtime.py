"""Extract and validate the exact shipped frozen runtime archive before execution."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.release_manifest import sha256_file


def extract_runtime(
    archive: Path, manifest_path: Path, destination: Path
) -> tuple[Path, dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text())
    if sha256_file(archive) != manifest["archive_sha256"]:
        raise ValueError("Runtime arşivi manifest kimliğiyle uyuşmuyor.")
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as stream:
        stream.extractall(destination, filter="data")
    verify_runtime_files(destination, manifest)
    entry = destination / manifest["entrypoint"]
    if entry.parent != destination or not entry.is_file() or entry.is_symlink():
        raise ValueError("Runtime giriş noktası geçersiz.")
    return entry.resolve(), manifest


def verify_runtime_files(destination: Path, manifest: dict[str, Any]) -> None:
    """Recheck immutable extracted bytes before and after actor execution."""
    expected = {item["path"]: item for item in manifest["files"]}
    actual = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_symlink() or path.is_file()
    }
    if actual != set(expected):
        raise ValueError("Runtime dosya kapsamı manifestle uyuşmuyor.")
    for relative, item in expected.items():
        parsed = PurePosixPath(relative)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("Runtime manifestinde kök dışı yol.")
        path = destination / relative
        if not path.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Runtime bağlantısı paket dışına çıkıyor.")
        if item["kind"] == "symlink":
            if not path.is_symlink() or str(path.readlink()) != item["target"]:
                raise ValueError("Runtime bağlantı kimliği uyuşmuyor.")
        elif item["kind"] != "file" or path.is_symlink() or sha256_file(path) != item["sha256"]:
            raise ValueError("Runtime dosya özeti uyuşmuyor.")

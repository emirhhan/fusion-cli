"""Yanlış proje metadata'sı paketlenmeden ve önceki çıktı silinmeden reddedilir."""

import json
import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest
from desktop_build.runtime import build_runtime as builder

from fusion_cli import __version__ as source_version


def test_builder_remains_directly_executable(tmp_path):
    repo = Path(builder.__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(Path(builder.__file__).resolve()), "--help"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(repo / "src")},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--output" in result.stdout


@pytest.mark.parametrize(
    "installed,imported", [("0.7.18", None), (None, None), ("0.7.18", "0.7.18")]
)
def test_metadata_mismatch_preserves_previous_output(tmp_path, monkeypatch, installed, imported):
    output = tmp_path / "output"
    output.mkdir()
    previous = output / "fusion-runtime.tar.gz"
    previous.write_bytes(b"previous verified package")
    work = tmp_path / "work"
    work.mkdir()
    sentinel = work / "keep"
    sentinel.write_bytes(b"previous build")

    def version(_distribution):
        if installed is None:
            raise metadata.PackageNotFoundError("fusion-cli")
        return installed

    monkeypatch.setattr(metadata, "version", version)
    if imported is not None:
        monkeypatch.setattr(builder, "__version__", imported, raising=False)
    monkeypatch.setattr(
        builder, "_run_pyinstaller", lambda *_: pytest.fail("Invalid metadata reached PyInstaller")
    )
    with pytest.raises(RuntimeError, match="metadata"):
        builder.build_runtime(output, work)
    assert previous.read_bytes() == b"previous verified package"
    assert sentinel.read_bytes() == b"previous build"


def test_manifest_uses_checkout_source_even_if_imported_version_is_stale(tmp_path, monkeypatch):
    expected = source_version
    monkeypatch.setattr(builder, "__version__", "0.7.18", raising=False)
    monkeypatch.setattr(metadata, "version", lambda _: expected)
    monkeypatch.setattr(builder.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(builder.platform, "machine", lambda: "arm64")

    def fake_pyinstaller(dist, _build):
        bundle = dist / "fusion-runtime"
        bundle.mkdir(parents=True)
        (bundle / "fusion").write_bytes(b"synthetic executable")

    monkeypatch.setattr(builder, "_run_pyinstaller", fake_pyinstaller)
    _, manifest = builder.build_runtime(tmp_path / "output", tmp_path / "work")
    assert json.loads(manifest.read_text())["runtime_version"] == expected

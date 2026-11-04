"""Yanlış proje metadata'sı paketlenmeden ve önceki çıktı silinmeden reddedilir."""

import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest
from desktop_build.runtime import build_runtime as builder


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


@pytest.mark.parametrize("installed", ["0.7.18", None])
def test_metadata_mismatch_preserves_previous_output(tmp_path, monkeypatch, installed):
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
    monkeypatch.setattr(
        builder, "_run_pyinstaller", lambda *_: pytest.fail("Invalid metadata reached PyInstaller")
    )
    with pytest.raises(RuntimeError, match="metadata"):
        builder.build_runtime(output, work)
    assert previous.read_bytes() == b"previous verified package"
    assert sentinel.read_bytes() == b"previous build"

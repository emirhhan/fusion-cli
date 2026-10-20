"""Replace öncesi/sonrası hata ve aynı süreç writer temp sahipliği."""

from __future__ import annotations

import errno
import json
import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from fusion_cli.core.atomic_file import AtomicCommitUncertainError, atomic_replace_text


def test_file_fsync_failure_keeps_old_content(tmp_path, monkeypatch):
    target = tmp_path / "record.json"
    target.write_text("old")

    def fail(_descriptor):
        raise OSError(errno.EIO, "fixture")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        atomic_replace_text(target, "new")
    assert target.read_text() == "old"
    assert not tuple(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(os.name == "nt", reason="Directory fsync bu platformda uygulanmıyor.")
def test_directory_fsync_failure_reports_already_committed(tmp_path, monkeypatch):
    target = tmp_path / "record.json"
    target.write_text("old")
    original = os.fsync

    def fail_directory(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(errno.EIO, "fixture")
        return original(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(AtomicCommitUncertainError) as raised:
        atomic_replace_text(target, "new")
    assert raised.value.committed
    assert target.read_text() == "new"
    assert not tuple(tmp_path.glob("*.tmp"))


def test_same_process_writers_have_independent_temporary_files(tmp_path, monkeypatch):
    target = tmp_path / "record.json"
    barrier = threading.Barrier(4)
    original = Path.replace
    temporary_paths = []

    def synchronized_replace(source, destination):
        temporary_paths.append(source)
        barrier.wait(timeout=2)
        return original(source, destination)

    monkeypatch.setattr(Path, "replace", synchronized_replace)
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(
            workers.map(
                lambda number: atomic_replace_text(target, json.dumps({"number": number})), range(4)
            )
        )
    assert len(set(temporary_paths)) == 4
    assert json.loads(target.read_text())["number"] in range(4)
    assert not tuple(tmp_path.glob("*.tmp"))

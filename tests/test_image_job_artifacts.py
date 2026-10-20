"""Kalıcı görsel makbuzu dosya kapsamı ve gerçek baytlarla doğrulanır."""

from __future__ import annotations

import errno
import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress

import pytest
from PIL import Image

from fusion_cli.appserver import image_job_artifacts as artifacts
from fusion_cli.core.image_jobs import ImageJobConflictError


def _image(path, color="blue"):
    Image.new("RGB", (12, 7), color).save(path)
    return {"ok": True, "saglayici": "offline", "dosyalar": [{"yol": str(path), "genislik": 999}]}


def test_receipt_uses_observed_dimensions_and_content_fingerprint(tmp_path):
    path = tmp_path / "image.png"
    (receipt,) = artifacts.collect_outputs(_image(path), tmp_path)
    assert (receipt.width, receipt.height) == (12, 7)
    assert receipt.digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert artifacts.outputs_current((receipt,), tmp_path)
    _image(path, "red")
    assert not artifacts.outputs_current((receipt,), tmp_path)


@pytest.mark.parametrize("kind", ["outside", "symlink", "invalid_image", "missing", "duplicate"])
def test_invalid_or_outside_artifact_never_becomes_output_receipt(tmp_path, kind):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    path = gallery / "image.png"
    result = _image(path)
    if kind == "outside":
        result = _image(tmp_path / "outside.png")
    elif kind == "symlink":
        outside = tmp_path / "outside.png"
        path.rename(outside)
        path.symlink_to(outside)
    elif kind == "invalid_image":
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
    elif kind == "missing":
        path.unlink()
    else:
        result["dosyalar"] *= 2
    with pytest.raises(ImageJobConflictError):
        artifacts.collect_outputs(result, gallery)


def test_artifact_read_limit_rejects_oversized_payload(tmp_path, monkeypatch):
    result = _image(tmp_path / "image.png")
    monkeypatch.setattr(artifacts, "MAX_IMAGE_JOB_BYTES", 10)
    with pytest.raises(ImageJobConflictError):
        artifacts.collect_outputs(result, tmp_path)


@pytest.mark.parametrize("retarget", ["parent", "leaf"])
def test_retarget_between_validation_and_open_never_reads_outside_bytes(
    tmp_path, monkeypatch, retarget
):
    gallery = tmp_path / "gallery"
    nested = gallery / "sub"
    nested.mkdir(parents=True)
    source = nested / "image.png"
    result = _image(source)
    outside = tmp_path / "outside"
    outside.mkdir()
    private = outside / "image.png"
    _image(private, "red")
    outside_inode = private.stat().st_ino
    original_open, original_fdopen = os.open, os.fdopen
    read_inodes = []
    changed = False

    def raced_open(path, flags, *args, **kwargs):
        nonlocal changed
        target = "sub" if retarget == "parent" else "image.png"
        if not changed and path == target:
            changed = True
            if retarget == "parent":
                nested.rename(gallery / "previous")
                nested.symlink_to(outside, target_is_directory=True)
            else:
                source.rename(nested / "previous.png")
                source.symlink_to(private)
        return original_open(path, flags, *args, **kwargs)

    def observed_fdopen(descriptor, *args, **kwargs):
        read_inodes.append(os.fstat(descriptor).st_ino)
        return original_fdopen(descriptor, *args, **kwargs)

    monkeypatch.setattr(artifacts.os, "open", raced_open)
    monkeypatch.setattr(artifacts.os, "fdopen", observed_fdopen)
    with pytest.raises(ImageJobConflictError):
        artifacts.collect_outputs(result, gallery)
    assert changed and outside_inode not in read_inodes


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO bu platformda yok")
@pytest.mark.parametrize("replace_at_open", [False, True])
def test_fifo_output_is_rejected_without_waiting_for_writer(tmp_path, monkeypatch, replace_at_open):
    path = tmp_path / "image.png"
    result = _image(path)
    opened = threading.Event()
    original_open = os.open
    if not replace_at_open:
        path.unlink()
        os.mkfifo(path)

    def fifo_open(name, flags, *args, **kwargs):
        if name == "image.png":
            if replace_at_open:
                path.unlink()
                os.mkfifo(path)
            opened.set()
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(artifacts.os, "open", fifo_open)
    with ThreadPoolExecutor(max_workers=1) as executor:
        worker = executor.submit(artifacts.collect_outputs, result, tmp_path)
        try:
            assert opened.wait(1)
            with pytest.raises(ImageJobConflictError):
                worker.result(timeout=0.2)
        finally:
            # Kırmızı sürümde blocking FIFO open'ı da gerçek writer ile aç;
            # testin kendi worker'ı başarısızlıkta bile geride kalmasın.
            try:
                writer = original_open(path, os.O_WRONLY | os.O_NONBLOCK)
            except OSError as error:
                if error.errno != errno.ENXIO:
                    raise
            else:
                os.close(writer)
            with suppress(ImageJobConflictError):
                worker.result(timeout=2)

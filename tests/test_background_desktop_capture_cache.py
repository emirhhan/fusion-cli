"""Arka plan PNG önbelleği, kilidi ve iptal/sahiplik sınırları."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import engine_tools
from fusion_cli.engines.agent.image_coordinates import ImageObservation
from fusion_cli.engines.agent.observation_delivery import internal_observation_paths

from .fakes import RecordingSink
from .image_fixture import image_bytes
from .test_agent_loop import _deps
from .test_background_desktop_image_handoff import _context, _snapshot


def _insert_marker(payload, value=b"1:" + b"a" * 32, *, corrupt=False):
    import struct
    import zlib

    chunk = b"tEXtFusionBackgroundCapture\0" + value
    crc = zlib.crc32(chunk) ^ int(corrupt)
    encoded = struct.pack(">I", len(chunk) - 4) + chunk + struct.pack(">I", crc)
    return payload[:-12] + encoded + payload[-12:]


@pytest.mark.parametrize("kind", ["corrupt", "duplicate", "version", "nonce", "mode"])
async def test_invalid_or_unprotected_marker_never_allows_overwrite(tmp_path, monkeypatch, kind):
    slot = tmp_path / ".fusion/tmp/arka-plan-ekrani.png"
    slot.parent.mkdir(parents=True)
    payload = _insert_marker(image_bytes("PNG"), corrupt=kind == "corrupt")
    if kind == "duplicate":
        payload = _insert_marker(payload)
    elif kind == "version":
        payload = _insert_marker(image_bytes("PNG"), value=b"2:" + b"a" * 32)
    elif kind == "nonce":
        payload = _insert_marker(image_bytes("PNG"), value=b"1:short")
    await asyncio.to_thread(slot.write_bytes, payload)
    slot.chmod(0o644 if kind == "mode" else 0o600)
    result = await _snapshot(monkeypatch, _context(tmp_path))
    assert "image_path" not in json.loads(result.output)
    assert await asyncio.to_thread(slot.read_bytes) == payload


async def test_forged_valid_marker_allows_cache_replace_but_never_owned_read(tmp_path, monkeypatch):
    slot = tmp_path / ".fusion/tmp/arka-plan-ekrani.png"
    slot.parent.mkdir(parents=True)
    await asyncio.to_thread(slot.write_bytes, _insert_marker(image_bytes("PNG")))
    slot.chmod(0o600)
    deps = _deps(tmp_path, RecordingSink())
    context = deps.tool_context
    context.desktop.begin_observation_turn("turn-one")
    result = await engine_tools._view_image_tool(deps).run({"path": str(slot)}, context)
    assert not result.ok
    result = await _snapshot(monkeypatch, context)
    assert json.loads(result.output)["image_path"] == str(slot)


async def test_marker_overhead_is_inside_total_image_budget(tmp_path, monkeypatch):
    from fusion_cli.tools import desktop_capture_io

    monkeypatch.setattr(desktop_capture_io, "MAX_BACKGROUND_BYTES", len(image_bytes("PNG")))
    result = await _snapshot(monkeypatch, _context(tmp_path))
    assert "image_path" not in json.loads(result.output)
    assert not (tmp_path / ".fusion/tmp/arka-plan-ekrani.png").exists()


async def test_marked_slot_wrong_uid_is_not_replaced(tmp_path, monkeypatch):
    import os

    slot = tmp_path / ".fusion/tmp/arka-plan-ekrani.png"
    slot.parent.mkdir(parents=True)
    payload = _insert_marker(image_bytes("PNG"))
    await asyncio.to_thread(slot.write_bytes, payload)
    slot.chmod(0o600)
    owner = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: owner + 1)
    result = await _snapshot(monkeypatch, _context(tmp_path))
    assert "image_path" not in json.loads(result.output)
    assert await asyncio.to_thread(slot.read_bytes) == payload


async def test_valid_marked_staging_recovers_after_process_exit(tmp_path, monkeypatch):
    staging = tmp_path / ".fusion/tmp/.arka-plan-ekrani.tmp"
    staging.parent.mkdir(parents=True)
    await asyncio.to_thread(staging.write_bytes, _insert_marker(image_bytes("PNG")))
    staging.chmod(0o600)
    result = await _snapshot(monkeypatch, _context(tmp_path))
    assert "image_path" in json.loads(result.output)
    assert not staging.exists()


def test_file_lease_relative_dir_fd_preserves_legacy_api(tmp_path):
    import os

    from fusion_cli.core.file_lease import FileLease

    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        first = FileLease(Path("capture.lock"), dir_fd=directory)
        second = FileLease(tmp_path / "capture.lock")
        assert first.try_acquire()
        assert not second.try_acquire()
        first.close()
        assert second.try_acquire()
        second.close()
    finally:
        os.close(directory)


async def test_partial_unknown_staging_is_preserved_with_inline_warning(tmp_path, monkeypatch):
    staging = tmp_path / ".fusion/tmp/.arka-plan-ekrani.tmp"
    staging.parent.mkdir(parents=True)
    await asyncio.to_thread(staging.write_bytes, b"unknown-partial")
    result = await _snapshot(monkeypatch, _context(tmp_path))
    assert "image_path" not in json.loads(result.output)
    assert await asyncio.to_thread(staging.read_bytes) == b"unknown-partial"


async def test_live_publication_lease_prevents_staging_cleanup(tmp_path, monkeypatch):
    from fusion_cli.core.file_lease import FileLease

    folder = tmp_path / ".fusion/tmp"
    folder.mkdir(parents=True)
    staging = folder / ".arka-plan-ekrani.tmp"
    payload = _insert_marker(image_bytes("PNG"))
    await asyncio.to_thread(staging.write_bytes, payload)
    staging.chmod(0o600)
    lease = FileLease(folder / ".arka-plan-ekrani.lock")
    assert lease.try_acquire()
    try:
        result = await _snapshot(monkeypatch, _context(tmp_path))
        assert "image_path" not in json.loads(result.output)
        assert await asyncio.to_thread(staging.read_bytes) == payload
    finally:
        lease.close()


@pytest.mark.parametrize("kind", ["symlink", "mode", "directory"])
def test_relative_lease_rejects_unsafe_file(tmp_path, kind):
    import os

    from fusion_cli.core.file_lease import FileLease

    lock = tmp_path / "capture.lock"
    if kind == "symlink":
        foreign = tmp_path / "foreign"
        foreign.write_bytes(b"user")
        lock.symlink_to(foreign)
    elif kind == "directory":
        lock.mkdir()
    else:
        lock.write_bytes(b"user")
        lock.chmod(0o644)
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        lease = FileLease(Path("capture.lock"), dir_fd=directory)
        with pytest.raises(OSError):
            lease.try_acquire()
        lease.close()
    finally:
        os.close(directory)


async def test_capture_without_owned_turn_does_not_publish(tmp_path, monkeypatch):
    result = await _snapshot(monkeypatch, ToolContext(tmp_path))
    assert "image_path" not in json.loads(result.output)
    assert result.images


@pytest.mark.parametrize("read_number", [1, 2])
@pytest.mark.parametrize("change", ["turn", "cancel", "receipt"])
async def test_read_await_cannot_lend_new_owner_a_stale_description(
    tmp_path, monkeypatch, read_number, change
):
    from fusion_cli.tools import desktop_capture_io

    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    path = json.loads(result.output)["image_path"]
    original = desktop_capture_io.read_background_image
    reads, calls = [], []

    def read(*args):
        uri = original(*args)
        reads.append(True)
        if len(reads) == read_number:
            if change == "turn":
                context.desktop.begin_observation_turn("changed-during-read")
            elif change == "cancel":
                context.cancelled.set()
            else:
                context.desktop.background_capture = None
        return uri

    async def describe(*args, **kwargs):
        calls.append(True)
        return ImageObservation("old-observation", None)

    monkeypatch.setattr(desktop_capture_io, "read_background_image", read)
    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    deps = _deps(tmp_path, RecordingSink())
    result = await engine_tools._view_image_tool(deps).run({"path": path}, context)
    assert not result.ok and "old-observation" not in result.output
    assert len(calls) == (0 if read_number == 1 else 1)


async def test_parent_symlink_revokes_internal_observation_accounting(tmp_path, monkeypatch):
    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    path = Path(json.loads(result.output)["image_path"])
    moved = tmp_path / "moved-cache"
    path.parent.rename(moved)
    path.parent.symlink_to(moved, target_is_directory=True)
    assert path not in internal_observation_paths(context, task="mevcut pencereyi incele")


@pytest.mark.parametrize("change", ["owner", "root", "receipt"])
async def test_accounting_rejects_revoked_background_owner(tmp_path, monkeypatch, change):
    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    path = Path(json.loads(result.output)["image_path"])
    if change == "owner":
        object.__setattr__(context, "job_scope", "revoked-owner")
    elif change == "root":
        object.__setattr__(context, "root", tmp_path / "new-root")
    else:
        context.desktop.background_capture = None
    assert path not in internal_observation_paths(context, task="pencereyi oku")


@pytest.mark.parametrize("has_receipt", [False, True])
@pytest.mark.parametrize("change", ["turn", "owner", "root", "receipt"])
async def test_classification_await_never_adopts_a_new_capture_owner(
    tmp_path, monkeypatch, has_receipt, change
):
    import threading

    from fusion_cli.tools import desktop_capture_io

    context = _context(tmp_path)
    path = tmp_path / desktop_capture_io.BACKGROUND_IMAGE_PATH
    if has_receipt:
        await _snapshot(monkeypatch, context)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def classify(*args):
        entered.set()
        assert release.wait(5)
        return True

    async def describe(*args, **kwargs):
        calls.append(True)
        return ImageObservation("new-owner-pixels", None)

    monkeypatch.setattr(desktop_capture_io, "is_background_slot", classify)
    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    deps = _deps(tmp_path, RecordingSink())
    task = asyncio.create_task(
        engine_tools._view_image_tool(deps).run({"path": str(path)}, context)
    )
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        if change == "turn":
            context.desktop.begin_observation_turn("new-turn")
        elif change == "owner":
            object.__setattr__(context, "job_scope", "new-owner")
        elif change == "root":
            root = tmp_path / "new-root"
            root.mkdir()
            object.__setattr__(context, "root", root)
        result = await _snapshot(monkeypatch, context, payload=image_bytes("PNG", (2, 2)))
        assert "image_path" in json.loads(result.output)
    finally:
        release.set()
    result = await task
    assert not result.ok and "new-owner-pixels" not in result.output
    assert not calls

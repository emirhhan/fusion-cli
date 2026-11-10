"""Arka plan gözlemi, teslim veya ön plan koordinat yetkisi vermez."""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from fusion_cli.core.desktop_frame import DesktopFrame
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import engine_tools
from fusion_cli.engines.agent.image_coordinates import ImageObservation
from fusion_cli.engines.agent.observation_delivery import internal_observation_paths
from fusion_cli.tools import desktop_background, native_desktop

from .fakes import RecordingSink
from .image_fixture import image_bytes
from .test_agent_loop import _deps


def _context(root: Path) -> ToolContext:
    context = ToolContext(root)
    context.desktop.begin_observation_turn("turn-one")
    return context


async def _snapshot(monkeypatch, context, *, payload=None, **metadata):
    payload = image_bytes("PNG") if payload is None else payload
    monkeypatch.setattr(
        native_desktop.SwiftDesktop,
        "invoke",
        AsyncMock(
            return_value={
                "ok": True,
                "kind": "window",
                "id": 2,
                "pid": 20,
                "image": "data:image/png;base64," + base64.b64encode(payload).decode(),
                **metadata,
            }
        ),
    )
    return await desktop_background.desktop_background_screenshot(
        {"window_id": 2, "pid": 20}, context
    )


async def test_text_only_background_image_has_owned_path_and_no_foreground_authority(
    tmp_path, monkeypatch
):
    deps = _deps(tmp_path, RecordingSink())
    deps.config = replace(deps.config, vision=ModelSpec("vision", "test/vision"))
    context = deps.tool_context
    context.desktop.begin_observation_turn("turn-one")
    frame = DesktopFrame(1, 1, 9, 9, 2, 2)
    context.desktop.frame = frame
    result = await _snapshot(monkeypatch, context)
    path = Path(json.loads(result.output)["image_path"])
    assert result.images
    assert (
        result.images[0] == "data:image/png;base64," + base64.b64encode(image_bytes("PNG")).decode()
    )
    assert b"FusionBackgroundCapture" in await asyncio.to_thread(path.read_bytes)
    assert context.desktop.frame is frame and context.desktop.current_capture is None
    assert not context.changes.paths and not context.touched
    assert path in internal_observation_paths(context, task="ekran görüntüsü üret")
    seen = []

    async def describe(config, data, question, **kwargs):
        seen.append((config.vision, data, kwargs))
        return ImageObservation("visible_text: 0; uncertainty: none", None)

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    observation = await engine_tools._view_image_tool(deps).run({"path": str(path)}, context)
    assert observation.ok and observation.visual_observation is None
    assert seen[0][0] == deps.config.vision


@pytest.mark.parametrize(
    "metadata,payload",
    [
        ({"id": 3}, None),
        ({"pid": 21}, None),
        ({"kind": "display"}, None),
        ({}, b"not-png"),
        ({}, b"x" * (5 * 1024 * 1024 + 1)),
    ],
)
async def test_invalid_capture_never_publishes_path(tmp_path, monkeypatch, metadata, payload):
    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context, payload=payload, **metadata)
    assert "image_path" not in json.loads(result.output)
    assert not (tmp_path / ".fusion/tmp/arka-plan-ekrani.png").exists()


async def test_other_owner_and_turn_cannot_borrow_capture(tmp_path, monkeypatch):
    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    path = json.loads(result.output)["image_path"]
    deps = _deps(tmp_path, RecordingSink())
    other = deps.tool_context
    other.desktop.begin_observation_turn("turn-one")
    tool = engine_tools._view_image_tool(deps)
    assert not (await tool.run({"path": path}, other)).ok
    context.desktop.begin_observation_turn("turn-two")
    assert not (await tool.run({"path": path}, context)).ok


async def test_same_bytes_overwritten_by_other_generation_are_not_owned(tmp_path, monkeypatch):
    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    path = Path(json.loads(result.output)["image_path"])
    replacement = tmp_path / "replacement.png"
    await asyncio.to_thread(replacement.write_bytes, await asyncio.to_thread(path.read_bytes))
    replacement.replace(path)
    deps = _deps(tmp_path, RecordingSink())
    observation = await engine_tools._view_image_tool(deps).run({"path": str(path)}, context)
    assert not observation.ok
    assert path not in internal_observation_paths(context, task="gözlemi oku")


@pytest.mark.parametrize("kind", ["file", "symlink", "parent-symlink"])
async def test_unowned_files_and_symlinks_are_never_overwritten(tmp_path, monkeypatch, kind):
    context = _context(tmp_path)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    original = foreign / "arka-plan-ekrani.png"
    original.write_bytes(b"user-file")
    slot = tmp_path / ".fusion/tmp/arka-plan-ekrani.png"
    slot.parent.parent.mkdir()
    if kind == "parent-symlink":
        slot.parent.symlink_to(foreign, target_is_directory=True)
    else:
        slot.parent.mkdir()
        if kind == "symlink":
            slot.symlink_to(original)
        else:
            slot.write_bytes(b"user-file")
    result = await _snapshot(monkeypatch, context)
    assert "image_path" not in json.loads(result.output)
    assert original.read_bytes() == b"user-file"
    assert slot.read_bytes() == b"user-file"


async def test_cancelled_capture_never_gets_a_receipt(tmp_path, monkeypatch):
    context = _context(tmp_path)
    context.cancelled.set()
    result = await _snapshot(monkeypatch, context)
    assert "image_path" not in json.loads(result.output)
    assert context.desktop.background_capture is None


async def test_old_foreground_capture_of_same_slot_never_gets_coordinate_credit(
    tmp_path, monkeypatch
):
    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    path = Path(json.loads(result.output)["image_path"])
    payload = await asyncio.to_thread(path.read_bytes)
    uri = "data:image/png;base64," + base64.b64encode(payload).decode()
    foreground = context.desktop.record_capture(path, uri, payload, (0, 0, 100, 100))
    deps = _deps(tmp_path, RecordingSink())

    async def describe(*args):
        return ImageObservation("visible_text: 0", None)

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    result = await engine_tools._view_image_tool(deps).run({"path": str(path)}, context)
    assert result.ok and result.visual_observation is None
    assert context.desktop.current_capture is foreground


@pytest.mark.parametrize("change", ["turn", "owner", "bytes", "cancel", "receipt"])
async def test_helper_response_cannot_outlive_owned_observation(tmp_path, monkeypatch, change):
    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    path = Path(json.loads(result.output)["image_path"])
    deps = _deps(tmp_path, RecordingSink())

    async def describe(*args):
        if change == "turn":
            context.desktop.begin_observation_turn("next-turn")
        elif change == "owner":
            object.__setattr__(context, "job_scope", "different-owner")
        elif change == "bytes":
            await asyncio.to_thread(path.write_bytes, b"changed")
        elif change == "cancel":
            context.cancelled.set()
        else:
            context.desktop.background_capture = None
        return ImageObservation("visible_text: old", None)

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    result = await engine_tools._view_image_tool(deps).run({"path": str(path)}, context)
    assert not result.ok and "visible_text: old" not in result.output


@pytest.mark.parametrize("alias", ["symlink", "hardlink", "case", "dot"])
async def test_reserved_slot_aliases_never_use_generic_file_reader(tmp_path, monkeypatch, alias):
    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    path = Path(json.loads(result.output)["image_path"])
    if alias == "symlink":
        alternate = tmp_path / "alias.png"
        alternate.symlink_to(path)
    elif alias == "hardlink":
        import os

        alternate = tmp_path / "alias.png"
        os.link(path, alternate)
    elif alias == "case":
        alternate = Path(str(path).replace("arka-plan", "ARKA-PLAN"))
    else:
        alternate = path.parent / ".." / "tmp" / path.name
    deps = _deps(tmp_path, RecordingSink())

    def generic(*args):
        pytest.fail("Özel gözlem yolu sıradan dosya okuyucusuna düştü")

    monkeypatch.setattr(engine_tools, "load_image_data_uri", generic)
    result = await engine_tools._view_image_tool(deps).run(
        {"path": str(alternate)}, deps.tool_context
    )
    assert not result.ok


async def test_task_cancellation_revokes_thread_publication_before_replace(tmp_path, monkeypatch):
    import asyncio
    import threading

    from fusion_cli.tools import desktop_capture_io

    context = _context(tmp_path)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_publish = desktop_background.publish_background_image

    def tracked_publish(*args):
        try:
            return original_publish(*args)
        finally:
            finished.set()

    monkeypatch.setattr(desktop_background, "publish_background_image", tracked_publish)
    original = desktop_capture_io.decode_png

    def held_decode(image):
        entered.set()
        assert release.wait(5)
        return original(image)

    monkeypatch.setattr(desktop_capture_io, "decode_png", held_decode)
    task = asyncio.create_task(_snapshot(monkeypatch, context))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    assert await asyncio.to_thread(finished.wait, 5)
    assert not (tmp_path / ".fusion/tmp/arka-plan-ekrani.png").exists()
    assert context.desktop.background_capture is None


async def test_real_vision_helper_keeps_configured_role_for_text_only_agent(tmp_path, monkeypatch):
    from .test_image_view_budget import _Provider, _result

    deps = _deps(tmp_path, RecordingSink(), agent=ModelSpec("agent", "fake/text"))
    vision = ModelSpec("vision", "fake/configured-vision")
    deps.config = replace(deps.config, vision=vision)
    context = deps.tool_context
    context.desktop.begin_observation_turn("current-turn")
    result = await _snapshot(monkeypatch, context)
    path = json.loads(result.output)["image_path"]
    provider = _Provider(_result(text="Kırmızı kare.", ok=True))
    seen = []

    def build(spec, **kwargs):
        seen.append(spec)
        return provider

    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", build)
    result = await engine_tools._view_image_tool(deps).run({"path": path}, context)
    assert result.ok and "Kırmızı kare" in result.output
    assert seen == [vision] and deps.config.agent.model == "fake/text"
    assert provider.seen[0].messages[-1].images
    assert result.visual_observation is None


async def test_failed_atomic_publish_has_no_path_or_new_files(tmp_path, monkeypatch):
    import os

    def fail(*args, **kwargs):
        raise OSError("test: publication unavailable")

    monkeypatch.setattr(os, "replace", fail)
    monkeypatch.setattr(os, "link", fail)
    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    assert "image_path" not in json.loads(result.output)
    assert [path.name for path in (tmp_path / ".fusion/tmp").iterdir()] == [
        ".arka-plan-ekrani.lock"
    ]
    assert context.desktop.background_capture is None


async def test_same_owner_can_reuse_only_fixed_slot_across_turns(tmp_path, monkeypatch):
    import stat

    context = _context(tmp_path)
    result = await _snapshot(monkeypatch, context)
    first = Path(json.loads(result.output)["image_path"])
    context.desktop.begin_observation_turn("next-turn")
    result = await _snapshot(monkeypatch, context, payload=image_bytes("PNG", (2, 2)))
    assert Path(json.loads(result.output)["image_path"]) == first
    assert sorted(path.name for path in first.parent.iterdir()) == [
        ".arka-plan-ekrani.lock",
        first.name,
    ]
    assert stat.S_IMODE((await asyncio.to_thread(first.stat)).st_mode) == 0o600
    assert json.loads(result.output)["image_width"] == 2


async def test_new_user_file_created_at_publish_boundary_is_not_overwritten(tmp_path, monkeypatch):
    import os

    from fusion_cli.tools import desktop_capture_io

    original = os.link
    slot = tmp_path / desktop_capture_io.BACKGROUND_IMAGE_PATH

    def race(*args, **kwargs):
        slot.write_bytes(b"user-file-created-after-precheck")
        return original(*args, **kwargs)

    monkeypatch.setattr(os, "link", race)
    result = await _snapshot(monkeypatch, _context(tmp_path))
    assert await asyncio.to_thread(slot.read_bytes) == b"user-file-created-after-precheck"
    assert "image_path" not in json.loads(result.output)


async def test_marked_stale_slot_is_reused_but_receipt_cannot_be_borrowed(tmp_path, monkeypatch):
    first_context = _context(tmp_path)
    result = await _snapshot(monkeypatch, first_context)
    path = Path(json.loads(result.output)["image_path"])
    old_payload = await asyncio.to_thread(path.read_bytes)
    deps = _deps(tmp_path, RecordingSink())
    second_context = deps.tool_context
    second_context.desktop.begin_observation_turn("turn-one")
    assert not (
        await engine_tools._view_image_tool(deps).run({"path": str(path)}, second_context)
    ).ok
    result = await _snapshot(monkeypatch, second_context)
    assert json.loads(result.output)["image_path"] == str(path)
    assert await asyncio.to_thread(path.read_bytes) != old_payload
    assert not (
        await engine_tools._view_image_tool(deps).run({"path": str(path)}, first_context)
    ).ok

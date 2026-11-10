"""Açık görsel okuma/tek hedef bulma niyeti, doğal dil tahminiyle değiştirilmez."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import engine_tools, image_view
from fusion_cli.engines.agent.image_coordinates import CoordinateStatus

from .fakes import RecordingSink, make_config
from .test_agent_loop import _deps
from .test_image_view_budget import _Provider, _result
from .test_vision_coordinate_contract import OMNI, _uri


def _provider(monkeypatch, text):
    provider = _Provider(replace(_result(text=text, ok=True), model=OMNI))
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda *_a, **_kw: provider)
    return provider, make_config(vision=ModelSpec("vision", OMNI))


@pytest.mark.parametrize("explicit", [False, True])
async def test_describe_keeps_original_prompt_and_visible_digits(monkeypatch, explicit):
    text = "visible_text: 17*23=; description: calculator; uncertainty: none"
    provider, config = _provider(monkeypatch, text)
    kwargs = {"mode": "describe"} if explicit else {}

    def forbidden_dimensions(*args):
        pytest.fail("describe modu koordinat boyut çözümlemesi başlattı")

    monkeypatch.setattr(image_view, "image_dimensions", forbidden_dimensions)
    observation = await image_view.describe_image_observation(
        config, _uri(), "Find the 2 button; read digits.", **kwargs
    )
    assert observation.usable and not observation.can_ground and text in observation.text
    assert "391" not in observation.text
    assert provider.seen[0].messages[0].content == image_view.VISION_GROUNDING_PROMPT


async def test_unexpected_point_in_default_describe_is_rejected(monkeypatch):
    _, config = _provider(monkeypatch, "<point>(500,500)</point>")
    observation = await image_view.describe_image_observation(config, _uri(), "Find a button.")
    assert observation.coordinates is CoordinateStatus.REJECTED
    assert not observation.usable and not observation.can_ground and not observation.text


async def test_explicit_locate_has_typed_point_and_local_contract(monkeypatch):
    provider, config = _provider(monkeypatch, "<point>(500,500)</point>")
    observation = await image_view.describe_image_observation(
        config, _uri(), "One button.", mode="locate"
    )
    assert observation.can_ground and observation.point.x == 684 and observation.point.y == 444.5
    assert "thousandths" in provider.seen[0].messages[0].content


@pytest.mark.parametrize("mode", [None, "", "auto", 1, [], {}])
async def test_invalid_tool_mode_fails_before_loading_or_provider(tmp_path, monkeypatch, mode):
    deps = _deps(tmp_path, RecordingSink())

    def forbidden(*args, **kwargs):
        pytest.fail("Geçersiz mod görsel veya sağlayıcı erişimine ulaştı")

    monkeypatch.setattr("fusion_cli.tools.desktop_capture_io.is_background_slot", forbidden)
    monkeypatch.setattr(engine_tools, "load_image_data_uri", forbidden)
    monkeypatch.setattr(engine_tools, "describe_image_data", forbidden)
    result = await engine_tools._view_image_tool(deps).run(
        {"path": "screen.png", "mode": mode}, deps.tool_context
    )
    assert not result.ok and "mode" in result.output


async def test_existing_tuple_wrappers_keep_default_describe(tmp_path, monkeypatch):
    from .image_fixture import image_bytes

    provider, config = _provider(monkeypatch, "visible_text: 17*23=")
    path = tmp_path / "screen.png"
    await asyncio.to_thread(path.write_bytes, image_bytes("PNG"))
    text, error = await image_view.describe_image(config, path, "Find 2.")
    assert error is None and "17*23=" in text
    assert provider.seen[0].messages[0].content == image_view.VISION_GROUNDING_PROMPT
    provider, config = _provider(monkeypatch, "<point>(500,500)</point>")
    text, error = await image_view.describe_image_data(config, _uri(), "Find 2.")
    assert not text and error
    assert provider.seen[0].messages[0].content == image_view.VISION_GROUNDING_PROMPT


async def test_background_locate_point_never_grants_or_revokes_foreground_authority(
    tmp_path, monkeypatch
):
    import json

    from .test_background_desktop_image_handoff import _snapshot
    from .test_desktop_visual_grounding import _capture

    deps = _deps(tmp_path, RecordingSink())
    deps.config = replace(deps.config, vision=ModelSpec("vision", OMNI))
    context = deps.tool_context
    context.desktop.begin_observation_turn("owned-turn")
    foreground, _ = _capture(deps)
    snapshot = await _snapshot(monkeypatch, context)
    provider, _ = _provider(monkeypatch, "<point>(500,500)</point>")
    result = await engine_tools._view_image_tool(deps).run(
        {"path": json.loads(snapshot.output)["image_path"], "mode": "locate"}, context
    )
    assert result.ok and "image_pixels" in result.output and result.visual_observation is None
    assert context.desktop.current_capture is foreground
    assert "thousandths" in provider.seen[0].messages[0].content


async def test_invalid_internal_mode_does_not_decode_or_call_provider(monkeypatch):
    config = make_config(vision=ModelSpec("vision", OMNI))

    def forbidden(*args, **kwargs):
        pytest.fail("Geçersiz mod sağlayıcı/boyut erişimine ulaştı")

    monkeypatch.setattr(image_view, "image_dimensions", forbidden)
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", forbidden)
    result = await image_view.describe_image_observation(config, _uri(), "Read.", mode="auto")
    assert not result.usable and result.error and "mode" in result.error


def test_blocked_click_recovery_requires_fresh_capture_and_explicit_single_target(tmp_path):
    from .test_desktop_visual_grounding import _preflight, _setup

    deps, state, _, _ = _setup(tmp_path)
    result = _preflight(deps, state)
    assert result.startswith("Güncel ekran gözlemi bu işlemden önce modele ulaşmadı.")
    assert "yeni tam desktop_screenshot" in result
    assert "view_image(path, mode='locate', question='<TEK kontrol>')" in result
    assert "describe" in result and "yetkisi vermez" in result
    assert "sonraki model adımında" in result
    assert "izin veriyorsa" in result
    assert "view_image(path, question)" not in result


@pytest.mark.parametrize("explicit", [False, True])
async def test_foreground_describe_reports_revocation_without_authorizing_clicks(
    tmp_path, monkeypatch, explicit
):
    from fusion_cli.engines.agent.image_coordinates import ImageObservation

    from .test_desktop_visual_grounding import _capture, _preflight, _setup

    deps, state, _, _ = _setup(tmp_path)
    capture, _ = _capture(deps)

    async def describe(*args, **kwargs):
        assert kwargs["mode"] == "describe"
        return ImageObservation("visible_text: 29")

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    args = {"path": str(capture.path), "question": "Find the 2 button."}
    if explicit:
        args["mode"] = "describe"
    result = await engine_tools._view_image_tool(deps).run(args, deps.tool_context)
    assert result.ok and "visible_text: 29" in result.output
    assert "Yalnız açıklama (mode=describe)" in result.output
    assert "tıklama koordinatı yetkisi vermez" in result.output
    assert "önceki ekran gözlemi geçersizleşti" in result.output
    assert "yeni tam desktop_screenshot" in result.output
    assert "view_image(path, mode='locate', question='<TEK kontrol>')" in result.output
    assert result.visual_observation is None
    assert deps.tool_context.desktop.current_capture is None
    assert state.desktop_grounding.acknowledged is None
    assert _preflight(deps, state) is not None


@pytest.mark.parametrize(
    "change", ["asset", "background", "capture", "file", "cancel", "root", "scope", "desktop"]
)
async def test_describe_does_not_mislabel_noncurrent_or_unowned_images(
    tmp_path, monkeypatch, change
):
    import json

    from fusion_cli.engines.agent.image_coordinates import ImageObservation

    from .image_fixture import image_bytes
    from .test_background_desktop_image_handoff import _snapshot
    from .test_desktop_visual_grounding import _capture, _setup

    deps, state, _, _ = _setup(tmp_path)
    context = deps.tool_context
    capture, _ = _capture(deps)
    original_desktop = context.desktop
    path = capture.path
    if change == "asset":
        path = tmp_path / "asset.png"
        path.write_bytes(image_bytes("PNG"))
    elif change == "background":
        context.desktop.begin_observation_turn("owned-turn")
        snapshot = await _snapshot(monkeypatch, context)
        path = json.loads(snapshot.output)["image_path"]

    async def describe(*args, **kwargs):
        if change == "capture":
            _capture(deps, name="new.png")
        elif change == "file":
            capture.path.write_bytes(image_bytes("PNG", (2, 2)))
        elif change == "cancel":
            context.cancelled.set()
        elif change == "root":
            object.__setattr__(context, "root", tmp_path / "other")
        elif change == "scope":
            object.__setattr__(context, "job_scope", "other")
        elif change == "desktop":
            object.__setattr__(
                context, "desktop", _deps(tmp_path, RecordingSink()).tool_context.desktop
            )
        return ImageObservation("visible_text: 29")

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    result = await engine_tools._view_image_tool(deps).run({"path": str(path)}, context)
    assert "Yalnız açıklama (mode=describe)" not in result.output
    assert "yeni tam desktop_screenshot" not in result.output
    assert result.visual_observation is None
    assert state.desktop_grounding.acknowledged is None
    if change in {"asset", "background", "cancel", "root", "scope", "desktop"}:
        assert original_desktop.current_capture is capture
    if change in {"cancel", "root", "scope", "desktop"}:
        assert not result.ok


@pytest.mark.parametrize("change", ["capture", "generation", "focus", "cancel"])
async def test_foreground_describe_status_rechecks_final_file_await(
    tmp_path, monkeypatch, change
):
    from fusion_cli.engines.agent.image_coordinates import ImageObservation

    from .test_desktop_visual_grounding import _capture, _setup

    deps, state, _, _ = _setup(tmp_path)
    context = deps.tool_context
    capture, _ = _capture(deps)
    original_matches = engine_tools.capture_file_matches

    async def describe(*args, **kwargs):
        return ImageObservation("visible_text: 29")

    def matches(observation, tool_context):
        matched = original_matches(observation, tool_context)
        if change == "capture":
            _capture(deps, name="new.png")
        elif change == "generation":
            context.desktop.invalidate_capture()
        elif change == "focus":
            context.desktop.focused_window_title = "Changed"
        else:
            context.cancelled.set()
        return matched

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    monkeypatch.setattr(engine_tools, "capture_file_matches", matches)
    result = await engine_tools._view_image_tool(deps).run({"path": str(capture.path)}, context)
    assert "Yalnız açıklama (mode=describe)" not in result.output
    assert result.visual_observation is None
    assert state.desktop_grounding.acknowledged is None
    if change == "cancel":
        assert not result.ok

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

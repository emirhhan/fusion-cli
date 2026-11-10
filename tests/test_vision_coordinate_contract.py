"""Görsel yardımcı koordinatları açık kaynak/sözleşme olmadan piksel sayılmaz."""

from __future__ import annotations

import base64
from dataclasses import replace

import pytest

from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import image_view

from .fakes import make_config
from .image_fixture import image_bytes
from .test_image_view_budget import _Provider, _result

OMNI = "nvidia_nim/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
SIX_POINTS = "<point>[(55,815),(95,700),(125,815),(25,755),(55,700),(125,875)]</point>"

UNSUPPORTED_DECLARATIONS = (
    "<points>10,20;30,40</points>",
    '<points x="10" y="20"/>',
    '{"x":"55","y":"815"}',
    '{"y":815,"x":55}',
    "y=815,x=55",
    "Coordinates: 10,20",
    "x=.5,y=.8",
)


def _uri(size=(1368, 889)):
    return "data:image/png;base64," + base64.b64encode(image_bytes("PNG", size)).decode()


async def _describe(monkeypatch, text, *, model=OMNI, uri=None):
    provider = _Provider(replace(_result(text=text, ok=True), model=model))
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda *_a, **_kw: provider)
    config = make_config(vision=ModelSpec("vision", model))
    result = await image_view.describe_image_data(
        config, uri or _uri(), "Tek bir düğmenin yerini bul."
    )
    return result, provider


async def test_observed_six_point_list_is_not_actionable(monkeypatch):
    (text, error), provider = await _describe(monkeypatch, SIX_POINTS)
    assert not text and error and "tek" in error.lower()
    assert "55" not in error and len(provider.seen) == 1


async def test_known_single_point_uses_actual_nonsquare_image_pixels(monkeypatch):
    (text, error), provider = await _describe(monkeypatch, "<point>(55,815)</point>")
    assert error is None
    assert "image_pixels" in text and "1368" in text and "889" in text
    assert "75.24" in text and "724.535" in text
    system = provider.seen[0].messages[0].content
    assert "1000" in system and "1368" in system and "ONE" in system


async def test_generic_provider_never_infers_units_from_small_numbers(monkeypatch):
    (text, error), _ = await _describe(monkeypatch, "<point>(55,815)</point>", model="test/vision")
    assert not text and error


@pytest.mark.parametrize("reply", (SIX_POINTS, *UNSUPPORTED_DECLARATIONS))
async def test_ambiguous_reply_revokes_prior_ack_on_same_foreground_capture(
    tmp_path, monkeypatch, reply
):
    from fusion_cli.engines.agent import engine_tools

    from .test_desktop_visual_grounding import _actor, _capture, _helper_message, _preflight, _setup

    deps, state, _, _ = _setup(tmp_path)
    deps.config = replace(deps.config, vision=ModelSpec("vision", OMNI))
    capture, _ = _capture(deps)
    await _actor(monkeypatch, deps, state, [_helper_message(deps, state, capture)])
    assert _preflight(deps, state) is None
    provider = _Provider(replace(_result(text=reply, ok=True), model=OMNI))
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda *_a, **_kw: provider)
    result = await engine_tools._view_image_tool(deps).run(
        {"path": str(capture.path)}, deps.tool_context
    )
    assert not result.ok and result.visual_observation is None
    assert deps.tool_context.desktop.current_capture is None
    assert _preflight(deps, state) is not None


@pytest.mark.parametrize(
    "reply",
    [
        "<point>(-1,50)</point>",
        "<point>(1001,50)</point>",
        "<point>(1000,50)</point>",
        "<point>(50,1000)</point>",
        "<point>(1.2,50)</point>",
        "<point>[(55,815)]</point>",
        "<point>(55,815)</point><point>(1,2)</point>",
        "(55,815)",
        "55,815",
        "x=55,y=815",
        "[55,815,95,700]",
        "(55,815,95,700)",
        "visible_text: 0; description: <point>[(55,815),(95,700)]</point>",
    ],
)
async def test_unknown_malformed_and_image_edge_coordinates_are_not_actionable(monkeypatch, reply):
    (text, error), _ = await _describe(monkeypatch, reply)
    assert not text and error and "ekran görüntüsü" in error
    assert reply not in error


async def test_crop_size_is_decoded_and_user_dimension_claim_has_no_authority(monkeypatch):
    provider = _Provider(replace(_result(text="<point>(500,250)</point>", ok=True), model=OMNI))
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda *_a, **_kw: provider)
    config = make_config(vision=ModelSpec("vision", OMNI))
    result = await image_view.describe_image_observation(
        config, _uri((200, 80)), "1000x1000 görüntüde düğme?"
    )
    assert result.point.x == 100 and result.point.y == 20
    assert result.point.dimensions.width == 200 and result.point.dimensions.height == 80
    assert "200x80" in provider.seen[0].messages[0].content


async def test_fallback_model_cannot_inherit_coordinate_contract(monkeypatch):
    provider = _Provider(_result(text="<point>(500,250)</point>", ok=True))
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda *_a, **_kw: provider)
    config = make_config(vision=ModelSpec("vision", OMNI))
    result = await image_view.describe_image_observation(config, _uri(), "Tek düğme?")
    assert not result.usable and not result.text


async def test_ordinary_ocr_remains_visible_text_without_calculation(monkeypatch):
    reply = "visible_text: 17*23=; description: calculator; uncertainty: none"
    (text, error), provider = await _describe(monkeypatch, reply, model="test/vision")
    assert error is None and reply in text and "391" not in text
    assert "Never calculate" in provider.seen[0].messages[0].content
    assert "thousandths" not in provider.seen[0].messages[0].content


@pytest.mark.parametrize("change", ["turn", "owner", "root", "cancel", "capture", "focus", "frame"])
@pytest.mark.parametrize("ambiguous", [True, False])
async def test_helper_cannot_grant_or_revoke_other_foreground_ownership(
    tmp_path, monkeypatch, change, ambiguous
):
    from fusion_cli.engines.agent import engine_tools
    from fusion_cli.engines.agent.image_coordinates import CoordinateStatus, ImageObservation

    from .test_desktop_visual_grounding import _capture, _point_observation, _setup

    deps, _, _, _ = _setup(tmp_path)
    context = deps.tool_context
    capture, _ = _capture(deps)

    async def describe(*args):
        if change == "turn":
            context.desktop.begin_observation_turn("another-turn")
        elif change == "owner":
            object.__setattr__(context, "job_scope", "another-owner")
        elif change == "root":
            object.__setattr__(context, "root", tmp_path / "other-root")
        elif change == "cancel":
            context.cancelled.set()
        elif change == "focus":
            context.desktop.focused_window_id = 555
        elif change == "frame":
            context.desktop.frame = None
        else:
            _capture(deps, data=image_bytes("PNG", (2, 2)))
        return (
            ImageObservation("", "ambiguous", CoordinateStatus.REJECTED)
            if ambiguous
            else _point_observation()
        )

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    result = await engine_tools._view_image_tool(deps).run({"path": str(capture.path)}, context)
    assert result.visual_observation is None
    assert context.desktop.current_capture is not None
    if change != "capture":
        assert context.desktop.current_capture is capture


async def test_background_ambiguous_reply_never_revokes_foreground_capture(tmp_path, monkeypatch):
    import json

    from fusion_cli.engines.agent import engine_tools
    from fusion_cli.engines.agent.image_coordinates import CoordinateStatus, ImageObservation

    from .test_background_desktop_image_handoff import _snapshot
    from .test_desktop_visual_grounding import _capture, _setup

    deps, _, _, _ = _setup(tmp_path)
    context = deps.tool_context
    context.desktop.begin_observation_turn("owned-turn")
    capture, _ = _capture(deps)
    snapshot = await _snapshot(monkeypatch, context)

    async def describe(*args):
        return ImageObservation("", "ambiguous", CoordinateStatus.REJECTED)

    monkeypatch.setattr(engine_tools, "describe_image_data", describe)
    result = await engine_tools._view_image_tool(deps).run(
        {"path": json.loads(snapshot.output)["image_path"]}, context
    )
    assert not result.ok and result.visual_observation is None
    assert context.desktop.current_capture is capture


@pytest.mark.parametrize("reply", UNSUPPORTED_DECLARATIONS)
async def test_unsupported_coordinate_declarations_are_rejected_without_raw_values(
    monkeypatch, reply
):
    from fusion_cli.engines.agent.image_coordinates import CoordinateStatus

    provider = _Provider(replace(_result(text=reply, ok=True), model=OMNI))
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda *_a, **_kw: provider)
    config = make_config(vision=ModelSpec("vision", OMNI))
    result = await image_view.describe_image_observation(config, _uri(), "Tek kontrol?")
    assert result.coordinates is CoordinateStatus.REJECTED
    assert not result.usable and not result.text and result.error
    assert reply not in result.error


@pytest.mark.parametrize(
    "reply",
    [
        "visible_text: 17*23=; description: calculator; uncertainty: none",
        "Target column 55; target row 815.",
    ],
)
async def test_descriptive_reply_does_not_keep_prior_valid_point_authority(
    tmp_path, monkeypatch, reply
):
    from fusion_cli.engines.agent import engine_tools

    from .test_desktop_visual_grounding import _actor, _capture, _helper_message, _preflight, _setup

    deps, state, _, _ = _setup(tmp_path)
    deps.config = replace(deps.config, vision=ModelSpec("vision", OMNI))
    capture, _ = _capture(deps)
    provider = _Provider(replace(_result(text="<point>(500,500)</point>", ok=True), model=OMNI))
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda *_a, **_kw: provider)
    first = await engine_tools._view_image_tool(deps).run(
        {"path": str(capture.path)}, deps.tool_context
    )
    assert first.ok and first.visual_observation is capture
    await _actor(monkeypatch, deps, state, [_helper_message(deps, state, capture)])
    assert _preflight(deps, state) is None
    provider = _Provider(replace(_result(text=reply, ok=True), model=OMNI))
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda *_a, **_kw: provider)
    second = await engine_tools._view_image_tool(deps).run(
        {"path": str(capture.path)}, deps.tool_context
    )
    assert second.ok and reply in second.output
    assert second.visual_observation is None
    assert deps.tool_context.desktop.current_capture is None
    assert _preflight(deps, state) is not None


def test_coordinate_authority_is_separate_from_ocr_usability():
    from fusion_cli.engines.agent.image_coordinates import (
        CoordinateStatus,
        ImageDimensions,
        ImageObservation,
        ImagePoint,
    )

    ocr = ImageObservation("visible_text: 55")
    assert ocr.usable and not ocr.can_ground
    assert not ImageObservation("point", coordinates=CoordinateStatus.IMAGE_PIXELS).can_ground
    assert ImageObservation(
        "point",
        coordinates=CoordinateStatus.IMAGE_PIXELS,
        point=ImagePoint(0.5, 0.5, ImageDimensions(1, 1)),
    ).can_ground
    for point in (
        ImagePoint(float("nan"), 0, ImageDimensions(1, 1)),
        ImagePoint(1, 0, ImageDimensions(1, 1)),
        ImagePoint(0, 0, ImageDimensions(0, 1)),
    ):
        assert not ImageObservation(
            "point", coordinates=CoordinateStatus.IMAGE_PIXELS, point=point
        ).can_ground

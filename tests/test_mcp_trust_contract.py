"""Paket 6: uzak annotation çelişkisinde ihtiyatlı Fusion kararı."""

from __future__ import annotations

import pytest
from mcp.types import ToolAnnotations

from fusion_cli.core.tools import ToolEffect
from fusion_cli.mcp_bridge.tool_effect import effect_from_annotations


@pytest.fixture(autouse=True)
def izole_kalici_bellek() -> None:
    """Saf sözleşme testinde ağır bellek temizleyicisini yükleme."""


def test_conflicting_read_and_destructive_hints_are_destructive() -> None:
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=True)

    assert effect_from_annotations(annotations) is ToolEffect.REMOTE_DESTRUCTIVE


def test_missing_annotations_do_not_grant_remote_read() -> None:
    assert effect_from_annotations(None) is ToolEffect.REMOTE_WRITE


def test_explicit_destructive_hint_is_not_downgraded() -> None:
    annotations = ToolAnnotations(readOnlyHint=False, destructiveHint=True)

    assert effect_from_annotations(annotations) is ToolEffect.REMOTE_DESTRUCTIVE


def test_conflicting_dynamic_ability_hints_are_destructive() -> None:
    from fusion_cli.mcp_bridge.ability_effects import effect_from_ability_meta

    assert (
        effect_from_ability_meta({"meta": {"annotations": {"readonly": True, "destructive": True}}})
        is ToolEffect.REMOTE_DESTRUCTIVE
    )

"""MCP araç açıklamaları → Fusion etki sınıfı."""

from __future__ import annotations

import pytest
from mcp.types import ToolAnnotations

from fusion_cli.core.tools import ToolEffect
from fusion_cli.mcp_bridge.tool_effect import effect_from_annotations


@pytest.mark.parametrize(
    ("annotations", "beklenen"),
    [
        (None, ToolEffect.REMOTE_WRITE),
        (ToolAnnotations(), ToolEffect.REMOTE_WRITE),
        (ToolAnnotations(readOnlyHint=True), ToolEffect.REMOTE_READ),
        (ToolAnnotations(readOnlyHint=True, destructiveHint=True), ToolEffect.REMOTE_READ),
        (ToolAnnotations(readOnlyHint=False, destructiveHint=True), ToolEffect.REMOTE_DESTRUCTIVE),
        (ToolAnnotations(destructiveHint=True), ToolEffect.REMOTE_DESTRUCTIVE),
        (ToolAnnotations(readOnlyHint=False, destructiveHint=False), ToolEffect.REMOTE_WRITE),
    ],
)
def test_mcp_aciklamasi_etki_sinifina_cevrilir(annotations, beklenen):
    assert effect_from_annotations(annotations) is beklenen

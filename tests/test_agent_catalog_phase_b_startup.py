"""Gerçek boyuttaki ajan açıklamasının başlangıç kataloğuna eksiksiz girmesi."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fusion_cli.tools.agent_catalog_index import agent_catalog_index
from fusion_cli.tools.capabilities import CapabilityRegistry


def test_gercek_buyuk_aciklama_frontmatter_sinirinda_kaybolmadan_uyarilir(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / ".claude/agents/buyuk.md"
    path.parent.mkdir(parents=True)
    description = "inceleme " * 6_000
    path.write_text(
        "---\nname: buyuk\ndescription: " + description + "\n---\nYALNIZ GÖVDE",
        encoding="utf-8",
    )
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path)
    with caplog.at_level(logging.WARNING):
        index = agent_catalog_index(registry, count_tokens=lambda text: len(text) // 3)

    agent = registry.get_agent("buyuk")
    assert agent is not None and agent.description == description.strip()
    assert description.strip() in index and "YALNIZ GÖVDE" not in index
    assert any(getattr(record, "token_sayisi", 0) > 15_000 for record in caplog.records)

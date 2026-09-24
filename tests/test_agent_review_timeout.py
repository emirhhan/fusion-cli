"""Öz-denetim sağlayıcı gecikse de kullanıcı cevabını bekletmemeli."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from fusion_cli.config.loader import load_config
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import review


@pytest.mark.asyncio
async def test_web_denetci_istegi_zaman_asiminda_turu_bekletmez(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")
    config = load_config(config_path)
    config = replace(config, runtime=replace(config.runtime, judge_timeout_s=0.01))

    async def slow_review(prompt, config, publisher):
        await asyncio.sleep(10)

    monkeypatch.setattr(review, "_ask", slow_review)
    result = await asyncio.wait_for(
        review.review_turn("Görev", "Cevap", [Message("user", "Görev")], config=config),
        timeout=3,
    )

    assert result == ""

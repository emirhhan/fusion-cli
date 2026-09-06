"""Artifact deposu gerçek araç yoluna bağlı.

Depo tek başına işe yaramaz: büyük çıktı üreten çağrı bu yoldan geçmeli ve model
özet + dosya yolu görmeli. Kanıt zinciri de bozulmamalı — çıktı kaybolmaz, yer
değiştirir.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fusion_cli.core.artifacts import ArtifactStore
from fusion_cli.core.tools import Tool, ToolContext, ToolResult
from fusion_cli.tools.registry import ToolRegistry


def _buyuk_arac() -> Tool:
    def _run(args, context):
        return ToolResult("X" * 60_000)

    return Tool(
        name="buyuk_cikti",
        description="Büyük çıktı üretir.",
        parameters={"type": "object", "properties": {}},
        run=_run,
    )


@pytest.mark.asyncio
async def test_buyuk_cikti_artifacta_alinir(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(_buyuk_arac())
    context = ToolContext(root=tmp_path, artifacts=ArtifactStore(tmp_path / ".fusion" / "art"))

    sonuc = await registry.execute("buyuk_cikti", {}, context)

    assert sonuc.artifact_path
    yol = Path(sonuc.artifact_path)
    assert await asyncio.to_thread(yol.is_file)
    assert len(sonuc.output) < 10_000
    assert "read_file" in sonuc.output


@pytest.mark.asyncio
async def test_depo_yoksa_cikti_degismez(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(_buyuk_arac())

    sonuc = await registry.execute("buyuk_cikti", {}, ToolContext(root=tmp_path))

    assert not sonuc.artifact_path
    assert len(sonuc.output) == 60_000

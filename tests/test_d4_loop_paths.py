"""Doğrulama düzeltme geçişi ve canlılık iptal ağacı için hedefli testler (A2-42)."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import liveness, loop

from .test_ask_teacher import _deps


def test_dogrulama_duzeltmesi_ilk_yedek_modele_gecer(tmp_path):
    asil = _deps(
        tmp_path,
        agent=ModelSpec(name="a", model="x/ana", fallback=("y/yedek", "z/son")),
        task_model_map={},
    )

    kopya = loop._verification_correction_deps(asil)

    assert kopya is not asil
    assert kopya.config.agent.model == "y/yedek" and kopya.config.agent.fallback == ("z/son",)
    assert asil.config.agent.model == "x/ana"  # orijinal bozulmaz


def test_yedegi_olmayan_modelde_ayni_deps_doner(tmp_path):
    asil = _deps(tmp_path, agent=ModelSpec(name="a", model="x/ana"), task_model_map={})

    assert loop._verification_correction_deps(asil) is asil


async def test_bekci_sagliksiz_derse_tuketici_iptal_edilir(monkeypatch):
    iptal: list[bool] = []

    async def _tuketici() -> None:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            iptal.append(True)
            raise

    async def _bekci(chunks, ping):
        return "sunucu yanıt vermiyor"

    monkeypatch.setattr(liveness, "watch", _bekci)
    monkeypatch.setattr(liveness, "ping_for", lambda spec: None)
    durum = loop._State()

    with pytest.raises(TimeoutError, match="yanıt vermiyor"):
        await loop._consume_with_liveness(_tuketici, ModelSpec(name="a", model="x/y"), durum)

    assert iptal == [True]
    assert durum.unresponsive_reason == "sunucu yanıt vermiyor"


async def test_tuketici_biterse_bekci_iptal_edilir(monkeypatch):
    bekci_iptal: list[bool] = []

    async def _tuketici() -> None:
        return None

    async def _bekci(chunks, ping):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            bekci_iptal.append(True)
            raise
        return ""

    monkeypatch.setattr(liveness, "watch", _bekci)
    monkeypatch.setattr(liveness, "ping_for", lambda spec: None)

    await loop._consume_with_liveness(_tuketici, ModelSpec(name="a", model="x/y"), loop._State())

    assert bekci_iptal == [True]

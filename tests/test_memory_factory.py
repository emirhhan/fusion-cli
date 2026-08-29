"""Bellek kurulumunun maliyeti: hangi yol neyi kurmak ZORUNDA."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.memory import factory

from .fakes import make_config


def test_performans_bellegi_gomme_fonksiyonu_kurmaz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`fusion stats` yalnız performans tablosunu okur; gömme kurulumu AĞA ÇIKAR.

    `build_embedding_function` NIM sağlayıcısında bir yoklama isteği gönderiyor
    (`memory/embeddings.py:90`). Model performans tablosunu görmek isteyen
    kullanıcı bunun bedelini ödememeli: ne gecikme, ne kota, ne ağ zorunluluğu.
    """

    def patlayan(*args: object, **kwargs: object) -> tuple[object, str]:
        raise AssertionError("stats yolunda gömme fonksiyonu kurulmamalı")

    monkeypatch.setattr(factory, "build_embedding_function", patlayan)

    memory = factory.build_performance_memory(make_config(memory_dir=tmp_path))

    assert memory.enabled
    assert memory.performance.stats() == ()

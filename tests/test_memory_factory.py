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


def test_kilitli_depo_turu_kilitlemez_bos_bellege_duser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Başka bir Fusion süreci depoyu tutuyorsa tur BEKLEMEZ, belleksiz devam eder.

    İki Fusion süreci aynı SQLite dosyasını açtığında ikincisi kilidi bekliyordu;
    kullanıcı sebebini göremeden turun donduğunu görüyordu. Bellek bir
    iyileştirmedir (bkz. `memory/factory.py` docstring): erişilemiyorsa doğru
    davranış beklemek değil, sebebi söyleyip belleksiz devam etmektir.
    """
    from fusion_cli.memory import store

    def asili_kalan(directory: Path) -> object:
        import time

        time.sleep(30)  # kilidi bekleyen süreç: asla dönmez
        raise AssertionError("buraya gelinmemeli")

    monkeypatch.setattr(store, "_create_client", asili_kalan)
    monkeypatch.setattr(store, "CLIENT_OPEN_TIMEOUT_S", 0.2)
    store.reset_clients()

    memory = factory.build_performance_memory(make_config(memory_dir=tmp_path))

    assert not memory.enabled
    assert "kilit" in (memory.unavailable_reason or "").lower()

"""Kaynak hatası boş katalog ya da sağlıklı model değildir."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from fusion_cli.appserver import model_catalog
from fusion_cli.cli.repl.model_flows import Source
from fusion_cli.config.keys import ProviderKeys
from fusion_cli.config.models import Config
from fusion_cli.providers.catalog import CatalogEntry


async def test_partial_catalog_failure_preserves_ready_rows_and_unknown_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken():
        raise ValueError("özel hata içeriği")

    sources = (
        Source("nim-free", "NIM", broken),
        Source(
            "openrouter-free",
            "OpenRouter",
            lambda: (CatalogEntry("openrouter/live", "openrouter"),),
        ),
    )
    monkeypatch.setattr(model_catalog.model_flows, "sources", lambda _: sources)
    monkeypatch.setattr(model_catalog, "detect", lambda: ProviderKeys(True, True))
    config = cast(
        Config, SimpleNamespace(runtime=SimpleNamespace(provider="auto"), tiers=(), web_sessions=())
    )
    result = await model_catalog.list_selectable_models(config)
    assert result["ok"] is True
    assert result["modeller"][0]["saglikli"] == "bilinmiyor"
    assert result["modeller"][0]["yetenek"]["reasoning_efforts_verified"] is False
    assert result["kaynak_hatalari"][0]["kaynak"] == "nim-free"
    assert "özel hata" not in str(result)


async def test_all_sources_failed_is_error_not_empty_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fusion_cli.providers.catalog import CatalogLoadResult

    source = Source(
        "nim-free",
        "NIM",
        lambda: (),
        loader=lambda: CatalogLoadResult(error="Model kataloğu okunamadı; yeniden dene."),
    )
    monkeypatch.setattr(model_catalog.model_flows, "sources", lambda _: (source,))
    monkeypatch.setattr(model_catalog, "detect", lambda: ProviderKeys(False, True))
    config = cast(
        Config, SimpleNamespace(runtime=SimpleNamespace(provider="auto"), tiers=(), web_sessions=())
    )
    result = await model_catalog.list_selectable_models(config)
    assert result["ok"] is False
    assert result["modeller"] == []
    assert result["kaynak_hatalari"]

"""Composer kataloğu yalnız gerçekten seçilebilir modelleri sunar."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from fusion_cli.appserver import model_catalog
from fusion_cli.cli.repl.model_flows import Source
from fusion_cli.config.keys import ProviderKeys
from fusion_cli.config.models import Config, WebSessionConfig
from fusion_cli.providers.catalog import CatalogEntry


def _config(*, sessions: tuple[WebSessionConfig, ...] = ()) -> Config:
    return cast(
        Config,
        SimpleNamespace(
            runtime=SimpleNamespace(provider="auto"),
            tiers=(),
            web_sessions=sessions,
        ),
    )


async def test_anahtar_olmayan_kaynak_katalog_istegi_yapmaz(monkeypatch):
    called: list[str] = []
    source = Source("openrouter-free", "OpenRouter", lambda: called.append("fetch") or ())
    monkeypatch.setattr(model_catalog.model_flows, "sources", lambda _config: (source,))
    monkeypatch.setattr(model_catalog, "detect", lambda: ProviderKeys(False, False))

    result = await model_catalog.list_selectable_models(_config())

    assert result == {"ok": True, "modeller": []}
    assert called == []


async def test_canli_model_ve_dogrulanmis_web_oturumu_listelenir(monkeypatch):
    source = Source(
        "openrouter-free",
        "OpenRouter ücretsiz",
        lambda: (CatalogEntry("openrouter/example/live", "openrouter"),),
    )
    monkeypatch.setattr(model_catalog.model_flows, "sources", lambda _config: (source,))
    monkeypatch.setattr(model_catalog, "detect", lambda: ProviderKeys(True, False))
    active = WebSessionConfig(
        model="chatgpt_web/main/auto", provider="chatgpt_web", login_verified=True
    )
    inactive = WebSessionConfig(
        model="claude_web/main/auto", provider="claude_web", login_verified=False
    )

    result = await model_catalog.list_selectable_models(_config(sessions=(active, inactive)))

    assert [row["model"] for row in result["modeller"]] == [
        "openrouter/example/live",
        "chatgpt_web/main/auto",
    ]
    assert result["modeller"][0]["kaynak"] == "openrouter-free"
    assert result["modeller"][1]["kaynak"] == "web-subscriptions"


async def test_aracsiz_ve_kademede_olmayan_nim_modeli_composera_girmez(monkeypatch):
    from fusion_cli.config.models import ModelSpec

    source = Source(
        "nim-free", "NIM", lambda: (
            CatalogEntry("nvidia_nim/selected", "nvidia_nim"),
            CatalogEntry("nvidia_nim/old", "nvidia_nim"),
        ),
    )
    paid = Source(
        "openrouter-free", "OpenRouter", lambda: (
            CatalogEntry("openrouter/chat-only", "openrouter", supports_tools=False),
        ),
    )
    monkeypatch.setattr(model_catalog.model_flows, "sources", lambda _config: (source, paid))
    monkeypatch.setattr(model_catalog, "detect", lambda: ProviderKeys(True, True))
    config = _config()
    config.tiers = (SimpleNamespace(
        name="high", agent=ModelSpec("agent", "nvidia_nim/selected"),
        judge=ModelSpec("judge", "nvidia_nim/selected"), candidates=(),
    ),)

    result = await model_catalog.list_selectable_models(config)

    assert [row["model"] for row in result["modeller"]] == ["nvidia_nim/selected"]


def test_yedek_model_birincil_oldugu_buyuk_gorev_grubunda_gorunur():
    from fusion_cli.config.models import ModelSpec

    config = _config()
    config.tiers = (
        SimpleNamespace(
            name="low",
            agent=ModelSpec("agent", "nvidia_nim/fast", fallback=("nvidia_nim/ultra",)),
            judge=ModelSpec("judge", "nvidia_nim/fast"),
            candidates=(),
        ),
        SimpleNamespace(
            name="ultra",
            agent=ModelSpec("agent", "nvidia_nim/ultra"),
            judge=ModelSpec("judge", "nvidia_nim/ultra"),
            candidates=(),
        ),
    )

    assert model_catalog._tier(config, "nvidia_nim/ultra") == "ultra"

"""Composer için yalnız bağlı ve canlı katalogda bulunan model seçenekleri."""

from __future__ import annotations

import asyncio
from typing import Any

from ..cli.repl import model_flows
from ..config.keys import ProviderPreference, detect
from ..config.models import Config
from ..providers.catalog import CatalogEntry


def _allowed_sources(config: Config) -> tuple[model_flows.Source, ...]:
    keys = detect()
    try:
        preference = ProviderPreference(str(config.runtime.provider).strip().lower())
    except ValueError:
        preference = ProviderPreference.AUTO
    allowed: list[model_flows.Source] = []
    for source in model_flows.sources(config):
        openrouter = (
            source.key.startswith("openrouter-")
            and keys.openrouter
            and preference is not ProviderPreference.NVIDIA
        )
        nim = (
            source.key == "nim-free"
            and keys.nim
            and preference is not ProviderPreference.OPENROUTER
        )
        if openrouter or nim:
            allowed.append(source)
    return tuple(allowed)


def _tier(config: Config, model_id: str) -> str:
    # Bir model alt kademenin yedeği de olabilir. Görünür görev grubu o
    # yedeklikten değil, modelin birincil seçildiği kademeden gelmeli.
    for tier in config.tiers:
        specs = (tier.agent, tier.judge, *tier.candidates)
        if any(model_id == spec.model for spec in specs):
            return tier.name
    for tier in config.tiers:
        specs = (tier.agent, tier.judge, *tier.candidates)
        if any(model_id in spec.models for spec in specs):
            return tier.name
    return "diger"


async def list_selectable_models(config: Config) -> dict[str, Any]:
    """Etkin anahtarı ve canlı katalog kaydı olmayan API modelini sunma.

    Tarayıcı oturumu yalnız ``auto`` modelini gerçekten destekliyorsa o gösterilir.
    Web arayüzünde henüz uygulanamayan bir model adı burada uydurulmaz.
    """
    sources = _allowed_sources(config)
    fetched = await asyncio.gather(
        *(asyncio.to_thread(source.fetcher) for source in sources if source.fetcher),
        return_exceptions=True,
    )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    curated_nim = {
        model
        for tier in config.tiers
        for spec in (tier.agent, tier.judge, *tier.candidates)
        for model in spec.models
    }
    for source, result in zip(sources, fetched, strict=True):
        if isinstance(result, BaseException):
            continue
        for entry in result:
            if not isinstance(entry, CatalogEntry) or entry.model_id in seen:
                continue
            # Composer ajan görevi başlatır: katalogda araç desteği açıkça
            # olmayan model ya da amaç dışı NIM modeli seçenek değildir.
            if entry.supports_tools is False:
                continue
            if source.key == "nim-free" and entry.model_id not in curated_nim:
                continue
            seen.add(entry.model_id)
            rows.append({
                "model": entry.model_id,
                "kaynak": source.key,
                "etiket": entry.model_id.split("/")[-1],
                "aciklama": source.label,
                "grup": _tier(config, entry.model_id),
            })
    for session in config.web_sessions:
        if not session.enabled or not session.login_verified or session.model in seen:
            continue
        seen.add(session.model)
        provider_name = session.provider.removesuffix("_web").title()
        model_name = session.selected_model or "otomatik"
        rows.append({
            "model": session.model,
            "kaynak": "web-subscriptions",
            "etiket": f"{provider_name} · {model_name}",
            "aciklama": f"{session.account} web oturumu",
            "grup": "web",
        })
    return {"ok": True, "modeller": rows}

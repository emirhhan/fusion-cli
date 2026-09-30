"""Composer için bağlı kaynakların canlı model kataloğu."""

from __future__ import annotations

import asyncio
from typing import Any

from ..cli.repl import model_flows
from ..config.keys import ProviderPreference, detect
from ..config.models import Config
from ..config.paths import user_data_dir
from ..config.tool_policy import mutation_policy_for_model
from ..providers import health_cache
from ..providers.catalog import CatalogEntry

#: Sağlıksız işaretli modelin açıklamasına eklenen uyarı. `doctor --live`
#: sondasının bulduğu, YAKIN ZAMANDA yanıt vermeyen model için.
_UNHEALTHY_SUFFIX = " (şu an yanıt vermiyor)"


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


async def list_selectable_models(
    config: Config, *, workspace_mode: str = "sohbet"
) -> dict[str, Any]:
    """Etkin anahtarı ve canlı katalog kaydı olmayan API modelini sunma.

    Tarayıcı oturumu yalnız ``auto`` modelini gerçekten destekliyorsa o gösterilir.
    Web arayüzünde henüz uygulanamayan bir model adı burada uydurulmaz.
    NIM katalog kaydı tek başına kullanılabilirlik kanıtı değildir: seçim anında
    gerçek araç çağrısı doğrulaması yapılır.

    `fusion doctor --live` sondasının bulduğu, YAKIN ZAMANDA yanıt vermeyen
    modeller burada GİZLENMEZ (sondaj eksik/eski olabilir) ama açıklamalarına
    uyarı eklenir ve listenin SONUNA alınır — seçici açılırken ikinci bir ağ
    çağrısı yapılmaz, yalnızca önceden yazılmış küçük bir dosya okunur.
    """
    sources = _allowed_sources(config)
    fetched = await asyncio.gather(
        *(asyncio.to_thread(source.fetcher) for source in sources if source.fetcher),
        return_exceptions=True,
    )
    health_path = user_data_dir() / health_cache.HEALTH_CACHE_FILENAME
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
            # Composer ajan görevi başlatır: araçsız olduğu bilinen model seçenek
            # değildir. NIM kataloğu araç yeteneği bildirmez; seçim anında canlı
            # araç sondası çalışır (commands._apply_development).
            if entry.supports_tools is False:
                continue
            seen.add(entry.model_id)
            unverified_nim = source.key == "nim-free" and entry.model_id not in curated_nim
            unhealthy = (
                source.key == "nim-free"
                and entry.model_id in curated_nim
                and (health_cache.is_known_unhealthy(health_path, entry.model_id))
            )
            aciklama = (
                "NIM kataloğunda; seçerken araç yeteneği doğrulanır"
                if unverified_nim
                else source.label
            )
            rows.append(
                {
                    "model": entry.model_id,
                    "kaynak": source.key,
                    "etiket": entry.model_id.split("/")[-1],
                    "aciklama": aciklama + _UNHEALTHY_SUFFIX if unhealthy else aciklama,
                    "grup": _tier(config, entry.model_id),
                    "saglikli": "hayir" if unhealthy else "evet",
                }
            )
    # Kararlı sıralama: yalnız sağlıksız işaretliler sona alınır, aksi hâlde
    # kaynakların/kayıtların ORİJİNAL sırası korunur.
    rows.sort(key=lambda row: row["saglikli"] == "hayir")
    for session in config.web_sessions:
        if not session.enabled or not session.login_verified or session.model in seen:
            continue
        if workspace_mode == "kod" and not mutation_policy_for_model(config, session.model).ok:
            continue
        seen.add(session.model)
        provider_name = session.provider.removesuffix("_web").title()
        model_name = session.selected_model or "otomatik"
        rows.append(
            {
                "model": session.model,
                "kaynak": "web-subscriptions",
                "etiket": f"{provider_name} · {model_name}",
                "aciklama": f"{session.account} web oturumu",
                "grup": "web",
            }
        )
    return {"ok": True, "modeller": rows}

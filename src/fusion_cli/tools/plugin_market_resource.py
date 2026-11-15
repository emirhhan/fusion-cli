"""Bildirilen kaynağı değişen pazarı yeni kaynaktan yeniden çek (Claude Code, #376).

Claude Code (loading.md "Plugins and marketplaces that aren't on disk"): `extraKnownMarketplaces`
girdisinin kaynağı kayıttakinden farklıysa pazar yeni kaynaktan yeniden çekilir. Pazar kaydı
yerinde güncellenir; o pazardan kurulu eklentiler kaldırılmaz (sonraki güncellemeleri yeni
katalogdan gelir). Yeni kaynaktaki pazarın adı aynı olmalıdır.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from ..config import plugin_store
from ..config.plugin_store import MarketplaceRecord, load_state, plugins_dir
from ..core.plugins import PluginError

ERR_NO_MARKET = "Pazar yok: {name}"
ERR_RENAMED = "Yeni kaynaktaki pazarın adı farklı ({old} → {new}); yeniden çekilmedi"


def resource_marketplace(name: str, spec: str, *, base: Path | None = None) -> MarketplaceRecord:
    from .plugin_install import fetch_market, read_marketplace
    from .plugin_market_source import KIND_GIT, KIND_URL, parse_market_source

    root = base or plugins_dir()
    record = load_state(root).marketplace(name)
    if record is None:
        raise PluginError(ERR_NO_MARKET.format(name=name))
    source = parse_market_source(spec)
    if source.kind in (KIND_GIT, KIND_URL):
        path = fetch_market(
            source.kind, source.location, source.ref, record.sparse, root, expected=name
        )
        stored = source.record_source
    else:
        market = read_marketplace(Path(source.location))
        if market.name != name:
            raise PluginError(ERR_RENAMED.format(old=name, new=market.name))
        path, stored = Path(source.location), source.location
    updated = replace(record, source=stored, kind=source.kind, path=str(path), added_at=time.time())
    plugin_store.update_state(lambda state: state.with_marketplace(updated), root)
    return updated

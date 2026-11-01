"""Masaüstü eklenti panelinin Claude `/plugin` eşdeğer alanları (#382, #394, #401, #397).

- `oturumluk`: `--plugin-dir`/`--plugin-url` (`<ad>@inline`) ve
  `~/.claude/skills/<ad>/.claude-plugin` (`<ad>@skills-dir`) eklentileri; kurulu değildir,
  kaldırılamaz (skills-dir aç/kapat `enabledPlugins`'e yazılır).
- `isaretli`: pazardan kaldırılıp otomatik kaldırılan ("Flagged") eklentiler; panelde görülünce
  `seenAt` yazılır.
- `bildirimler`: arka plan otomatik güncellemesi / pazar eşlemesi bildirimleri (bir kez verilir).
- pazar satırında `otomatik_guncelle` ve `eklenti.pazar_otomatik` ile Enable/Disable auto-update.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..config import plugin_store
from ..config.plugin_store import InstalledPlugin, MarketplaceRecord, load_state
from ..core.plugins import PluginError

ERR_NO_MARKET = "Pazar yok: {name}"


def _session_row(item: InstalledPlugin, scope: str) -> dict[str, Any]:
    layout = item.layout
    return {
        "ad": item.record.name,
        "kimlik": plugin_store.plugin_id(item.record),
        "kapsam": scope,
        "surum": item.record.version,
        "aciklama": layout.manifest.description if layout else "",
        "kaynak": item.record.source or (str(layout.root) if layout else ""),
    }


def session_rows(root: Path | None = None) -> list[dict[str, Any]]:
    from ..config.plugin_session import session_plugins
    from ..config.plugin_skills_dir import skills_dir_enabled, skills_dir_plugins

    project = root or Path.cwd()
    rows = [{**_session_row(item, "session"), "etkin": True} for item in session_plugins()]
    for item in skills_dir_plugins():
        enabled = skills_dir_enabled(item, project)
        rows.append({**_session_row(item, "skills-dir"), "etkin": enabled})
    return rows


def flagged_rows() -> list[dict[str, Any]]:
    from ..tools.plugin_flagged import load_flagged, mark_seen

    flagged = load_flagged()
    mark_seen(item.ident for item in flagged)
    return [
        {"kimlik": f.ident, "ad": f.name, "pazar": f.marketplace, "tarih": f.date} for f in flagged
    ]


def notices() -> list[str]:
    from ..tools.plugin_auto_update import drain_notices

    return list(drain_notices())


def _auto_update_on(record: MarketplaceRecord) -> bool:
    from ..tools.plugin_auto_update import is_auto_update
    from ..tools.plugin_declared import declared_marketplaces

    try:
        declared = declared_marketplaces(Path.cwd())
    except (OSError, PluginError):
        declared = {}
    return is_auto_update(record.name, declared, record.auto_update)


def market_rows() -> list[dict[str, Any]]:
    return [
        {
            "ad": m.name,
            "kaynak": m.source,
            "tur": m.kind,
            "otomatik_guncelle": _auto_update_on(m),
        }
        for m in load_state().marketplaces
    ]


def set_auto_update(data: Mapping[str, object]) -> None:
    """`/plugin` Marketplaces "Enable/Disable auto-update" karşılığı (pazar kaydına yazılır)."""
    name = str(data.get("ad") or "")
    record = load_state().marketplace(name)
    if record is None:
        raise PluginError(ERR_NO_MARKET.format(name=name))
    updated = replace(record, auto_update=data.get("acik") is True)
    plugin_store.update_state(lambda state: state.with_marketplace(updated))

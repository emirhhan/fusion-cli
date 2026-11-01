"""Proje ayarında açılan ama bu makinede kurulmamış eklentiler (#376).

Claude Code (https://code.claude.com/docs/en/plugins/loading.md "Enabled in project settings but
not installed"): `enabledPlugins` ile project/local dosyasında açılan `ad@pazar`, pazar girdisi
göreli yollu (relative-path) ise kurulum kaydı gerekmeden pazarın kendisinden yüklenir. Dış
kaynaklı girdi bu makineye çekilmez; `Plugin "<ad>" is enabled in project settings but isn't
installed here` bildirilir (Claude bunu `/plugin` Errors sekmesinde gösterir; Fusion günlüğe yazar).

Güvenlik: proje dosyasındaki `true` yalnız güvenilen dosyada geçerlidir (`plugin_scopes`).
Eklenti pazar kökünün dışına çıkamaz. Pazar girdisinin plugin.json alanları burada uygulanmaz.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.plugin_marketplace import Marketplace, MarketplaceEntry, parse_marketplace
from ..core.plugins import MARKETPLACE_PATHS, PluginError
from .plugin_scopes import SCOPE_LOCAL, SCOPE_PROJECT, resolve_enabled, scope_values

if TYPE_CHECKING:
    from .plugin_store import InstalledPlugin, MarketplaceRecord, PluginState

_LOG = logging.getLogger(__name__)

NOT_INSTALLED = 'Plugin "{name}" is enabled in project settings but isn\'t installed here'
_FILE_KIND = "dosya"


def _enabled_ids(root: Path) -> Iterator[str]:
    seen: set[str] = set()
    for scope in (SCOPE_LOCAL, SCOPE_PROJECT):
        for key, value in scope_values(scope, root).items():
            if value and "@" in key and key not in seen:
                seen.add(key)
                name = key.split("@", 1)[0]
                if resolve_enabled(key, name, False, root).enabled:
                    yield key


def _read_market(record: MarketplaceRecord) -> Marketplace | None:
    path = Path(record.path)
    candidates = [path] if path.is_file() else [path / item for item in MARKETPLACE_PATHS]
    for candidate in candidates:
        if candidate.is_file():
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
                return parse_marketplace(raw, where=candidate.name)
            except (OSError, ValueError, PluginError) as error:
                _LOG.warning("pazar '%s' okunamadı: %s", record.name, error)
                return None
    return None


def _market_root(record: MarketplaceRecord) -> Path:
    path = Path(record.path)
    return path.parent.parent if record.kind == _FILE_KIND else path


def _entry_folder(record: MarketplaceRecord, entry: MarketplaceEntry) -> Path | None:
    if entry.source.kind != "path":
        return None
    root = _market_root(record).resolve()
    folder = (root / entry.source.location).resolve()
    return folder if folder.is_relative_to(root) and folder.is_dir() else None


def _is_installed(state: PluginState, ident: str) -> bool:
    from .plugin_store import plugin_id

    return any(plugin_id(item) == ident or item.source == ident for item in state.plugins)


def project_enabled_plugins(
    state: PluginState, root: Path, taken: set[str], base: Path | None = None
) -> tuple[InstalledPlugin, ...]:
    """Proje/local'de açılmış, kurulmamış göreli eklentiler (kayıt yazılmaz)."""
    from dataclasses import replace

    from .plugin_store import PluginRecord, inspect_plugin

    found: list[InstalledPlugin] = []
    for ident in _enabled_ids(root):
        if _is_installed(state, ident):
            continue
        name, market_name = ident.split("@", 1)
        record = state.marketplace(market_name)
        market = _read_market(record) if record is not None else None
        entry = next((e for e in market.entries if e.name == name), None) if market else None
        folder = _entry_folder(record, entry) if record and entry else None
        if folder is None:
            _LOG.warning(NOT_INSTALLED.format(name=name))
            continue
        plugin = PluginRecord(
            name=name, source=ident, kind="pazar", marketplace=market_name, folder=str(folder)
        )
        item = inspect_plugin(plugin, base)
        if item.layout is None:
            _LOG.warning("eklenti '%s' yüklenmedi: %s", ident, item.detail)
            continue
        if item.layout.name in taken:
            continue
        taken.add(item.layout.name)
        found.append(replace(item, record=replace(plugin, name=item.layout.name)))
    return tuple(found)

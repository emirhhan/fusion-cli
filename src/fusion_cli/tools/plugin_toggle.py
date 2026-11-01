"""Kapsamlı aç/kapat, veri silen kaldırma, eklentileriyle pazar kaldırma (#376, #396, #408).

Claude Code (https://code.claude.com/docs/en/plugins/cli-reference.md):
- `plugin enable|disable <ad|ad@pazar> [--scope]` → "Successfully enabled plugin: x (scope: y)";
  zaten o durumdaysa `Plugin "x" is already enabled` ve çıkış 1.
- `plugin uninstall` son kapsamdan kaldırınca veri klasörünü siler; `--keep-data` korur.
- `plugin marketplace remove` o pazardan kurulan BÜTÜN eklentileri de kaldırır
  ("Also uninstalled N plugins from this marketplace:").
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from ..config import plugin_store
from ..config.plugin_data import plugin_data_dir
from ..config.plugin_scopes import (
    SCOPE_USER,
    check_scope,
    resolve_enabled,
    target_scope,
    write_enabled,
)
from ..config.plugin_store import PluginRecord, PluginState, load_state, plugin_id, plugins_dir
from ..core.plugins import PluginError

ERR_NOT_INSTALLED = "Kurulu değil: {name}"
ERR_ALREADY = 'Eklenti "{name}" zaten {state}'
ERR_AMBIGUOUS = "'{name}' birden çok pazardan kurulu: {ids}. ad@pazar biçimini kullan."
ERR_UNINSTALL_SCOPE = (
    'Eklenti kaldırılamadı "{name}": {scope} kapsamında kurulu değil '
    "(Fusion kurulumları user kapsamındadır)."
)


def find_record(state: PluginState, spec: str) -> PluginRecord:
    """`ad` ya da `ad@pazar` (Claude eklenti bağımsız değişkeni)."""
    name, _, market = spec.partition("@")
    matches = [
        r
        for r in state.plugins
        if name in (r.name, entry_name(r)) and (not market or r.marketplace == market)
    ]
    if not matches:
        raise PluginError(ERR_NOT_INSTALLED.format(name=spec))
    if len(matches) > 1:
        ids = ", ".join(sorted(plugin_id(r) for r in matches))
        raise PluginError(ERR_AMBIGUOUS.format(name=spec, ids=ids))
    return matches[0]


def entry_name(record: PluginRecord) -> str:
    """Pazar girdisinin adı (Claude kurma/açma anahtarı); bildirim adından farklı olabilir."""
    if record.marketplace and record.source.endswith(f"@{record.marketplace}"):
        return record.source.removesuffix(f"@{record.marketplace}")
    return record.name


@dataclass(frozen=True, slots=True)
class ToggleResult:
    name: str
    scope: str
    enabled: bool


def toggle_plugin(
    spec: str,
    enabled: bool,
    *,
    scope: str = "",
    base: Path | None = None,
    root: Path | None = None,
) -> ToggleResult:
    """Kapsamı algıla ya da denetle, hedef kapsamda zaten o durumdaysa hata, değilse yaz."""
    store = base or plugins_dir()
    project = root or Path.cwd()
    record = find_record(load_state(store), spec)
    ident = plugin_id(record)
    target = target_scope(ident, record.name, project, scope)
    current = resolve_enabled(ident, record.name, record.enabled, project, upto=target)
    if current.enabled == enabled:
        label = "açık" if enabled else "kapalı"
        raise PluginError(ERR_ALREADY.format(name=record.name, state=label))
    if target == SCOPE_USER:
        updated = replace(record, enabled=enabled)
        plugin_store.update_state(lambda state: state.with_plugin(updated), store)
    else:
        write_enabled(target, ident, record.name, enabled, project)
    return ToggleResult(record.name, target, enabled)


def check_uninstall_scope(spec: str, scope: str) -> None:
    """Fusion kurulumları yalnız user kapsamında: başka kapsam Claude gibi 'kurulu değil' der."""
    if scope and check_scope(scope) != SCOPE_USER:
        raise PluginError(ERR_UNINSTALL_SCOPE.format(name=spec, scope=scope))


def remove_plugin_data(name: str) -> bool:
    """Eklentinin kalıcı veri klasörünü (`${CLAUDE_PLUGIN_DATA}`) sil; silindiyse True."""
    folder = plugin_data_dir(name, create=False)
    if not folder.is_dir() or folder.is_symlink():
        return False
    shutil.rmtree(folder)
    return True


def plugins_from_marketplace(market: str, base: Path | None = None) -> tuple[str, ...]:
    """Bu pazardan kurulmuş eklentilerin adları (kaldırma sırasıyla)."""
    state = load_state(base or plugins_dir())
    return tuple(sorted(r.name for r in state.plugins if r.marketplace == market))

"""Eklenti kaydı sürüm 1 → 2 geçişi (#419, #392).

Sürüm 1'de kopyası kurulumdan sonra değişen eklenti 'değişmiş' sayılır ve yeniden onaylanana
dek hiç yüklenmezdi. Claude Code'da bu kilit yok (#392); kaldırılınca kullanıcının daha önce
onaylamayı reddettiği değişmiş içerik yükseltmeden sonra sessizce çalışırdı. Geçiş bir kez,
kayıt kilidi altında yapılır: o eklenti kapatılır ve günlüğe nasıl açılacağı yazılır. Kullanıcı
açınca Claude gibi yüklenir.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.plugins import PluginError
from .plugin_layout import tree_digest

if TYPE_CHECKING:
    from .plugin_store import PluginRecord, PluginState

_LOG = logging.getLogger(__name__)

WARN_MIGRATED = (
    "eklenti '{name}' kurulumdan sonra değişmiş görünüyor (eski 'değişmiş' kilidi); Claude "
    "Code'da bu kilit olmadığından kapatıldı. İçeriğini inceleyip `fusion plugin enable {name}` "
    "ile açın."
)


def _changed(record: PluginRecord, base: Path | None) -> bool:
    from .plugin_store import plugin_folder

    if record.folder or record.kind == "inline" or not record.digest or not record.enabled:
        return False
    folder = plugin_folder(record, base)
    if not folder.is_dir():
        return False
    try:
        return tree_digest(folder) != record.digest
    except (OSError, PluginError):
        return False


def migrated(state: PluginState, base: Path | None = None) -> PluginState:
    """Sürüm 1 kaydında değişmiş kopyaları kapat; güncel kayda dokunma."""
    from .plugin_store import STATE_VERSION

    if state.schema >= STATE_VERSION:
        return state
    plugins = []
    for record in state.plugins:
        if _changed(record, base):
            _LOG.warning(WARN_MIGRATED.format(name=record.name))
            record = replace(record, enabled=False)
        plugins.append(record)
    return replace(state, plugins=tuple(plugins), schema=STATE_VERSION)


def ensure_migrated(state: PluginState, base: Path | None = None) -> PluginState:
    """Okunan kayıt eskiyse geçişi kilit altında yazıp güncel kaydı döndür."""
    from .plugin_store import STATE_VERSION, update_state

    if state.schema >= STATE_VERSION or not state.plugins:
        return state
    return update_state(lambda current: current, base)

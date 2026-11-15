"""Eklenti kaydı sürüm geçişleri: 1 → 2 (#419, #392), 2 → 3 (#391 depolama anahtarı).

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


#: Kayıt sürümleri: 2'de 'değişmiş' kilidi kalktı (#392); 3'te veri/ayar kimlikle anahtarlanır.
_TAMPER_LOCK_DROPPED = 2
_STORAGE_BY_ID = 3


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
    """Eski kaydı güncel sürüme getir (1→2 değişmiş kopyalar, 2→3 depolama anahtarı)."""
    from .plugin_store import STATE_VERSION

    if state.schema >= STATE_VERSION:
        return state
    plugins = []
    for record in state.plugins:
        if state.schema < _TAMPER_LOCK_DROPPED and _changed(record, base):
            _LOG.warning(WARN_MIGRATED.format(name=record.name))
            record = replace(record, enabled=False)
        plugins.append(record)
    if state.schema < _STORAGE_BY_ID:
        _adopt_storage(tuple(plugins), base)
    return replace(state, plugins=tuple(plugins), schema=STATE_VERSION)


def _adopt_storage(records: tuple[PluginRecord, ...], base: Path | None) -> None:
    """Sürüm 3 (#391): adla yazılmış veri/ayar o adı ilk alan kurulumun kimliğine taşınır."""
    from .plugin_storage import adopt_legacy_storage
    from .plugin_store import plugins_dir

    for record in records:
        try:
            adopt_legacy_storage(record, base or plugins_dir())
        except OSError as error:
            _LOG.warning("eklenti '%s' verisi taşınamadı: %s", record.name, error)


def ensure_migrated(state: PluginState, base: Path | None = None) -> PluginState:
    """Okunan kayıt eskiyse geçişi kilit altında yazıp güncel kaydı döndür."""
    from .plugin_store import STATE_VERSION, update_state

    if state.schema >= STATE_VERSION or not state.plugins:
        return state
    return update_state(lambda current: current, base)

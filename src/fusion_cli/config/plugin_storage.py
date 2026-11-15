"""Kurulumun veri klasörü ve userConfig değerleri için depolama anahtarı (#391, #408).

Claude Code (plugins-reference "Environment variables"): `${CLAUDE_PLUGIN_DATA}` eklenti
kimliğiyle (`ad@pazar`) anahtarlanır. Farklı pazarlardan aynı adlı iki eklenti birlikte
kurulabildiği için (#391) veri klasörü, `pluginConfigs` girdisi ve sırlar da kimlikle
anahtarlanır; birini kaldırmak ötekinin verisine dokunmaz. Pazarsız (yerel/git/oturumluk)
kurulumda kimlik addır.

Eski sürüm bunları yalnız adla yazıyordu: kayıt sürümü 3'e geçerken (kayıt kilidi altında, bir
kez) o adı ilk alan kurulumun (`store_key == ad`) verisi ve ayarları kimliğine taşınır.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .plugin_data import plugin_data_dir

if TYPE_CHECKING:
    from .plugin_store import PluginRecord


def storage_key(record: PluginRecord) -> str:
    """Veri klasörü ve değer deposu anahtarı: Claude eklenti kimliği."""
    from .plugin_store import plugin_id

    return plugin_id(record)


def _same(left: Path, right: Path) -> bool:
    if left == right:
        return True
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def storage_key_for_root(root: Path, fallback: str, base: Path | None = None) -> str:
    """Kökü bu klasör olan kurulu eklentinin anahtarı; kayıtta yoksa `fallback` (ad).

    Oturumluk (`--plugin-dir`) ve proje eklentileri kayıtta yoktur; pazarsız oldukları için
    kimlikleri zaten adlarıdır.
    """
    from .plugin_store import load_state, plugin_folder

    for record in load_state(base).plugins:
        if _same(plugin_folder(record, base), root):
            return storage_key(record)
    return fallback


def adopt_legacy_storage(record: PluginRecord, base: Path) -> None:
    """Adla yazılmış eski veri ve ayarları kimliğe taşı (hedef varsa dokunma)."""
    from .plugin_user_config import rename_values

    key = storage_key(record)
    if key == record.name or record.store_key != record.name:
        return
    old, new = plugin_data_dir(record.name), plugin_data_dir(key)
    if old.is_dir() and not old.is_symlink() and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
    rename_values(record.name, key, base)

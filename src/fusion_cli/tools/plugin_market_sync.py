"""Pazarın `renames` ve `forceRemoveDeletedPlugins` alanlarını kuruluma uygula (Claude, #397).

Belge (code.claude.com/docs/en/plugins/host-marketplace.md, "Rename or remove a plugin"):
- `renames` eski adı yeni ada (ya da kaldırıldıysa `null`'a) eşler; zincir en eski addan izlenir.
  Yeniden adlandırılan kurulum yeni adla sürer, `enabledPlugins` anahtarı user/project/local
  kapsamlarında yeni ada yazılır ve bir kez `Renamed to "<yeni>" in the "<pazar>" marketplace`
  bildirilir. `null`'da anahtar düşer: `Removed from the "<pazar>" marketplace`.
- `forceRemoveDeletedPlugins: true` iken girdilerde de `renames`'te de olmayan kurulum
  kaldırılır ("Removed from marketplace"); alan yoksa kurulum kalır.

Fusion bunu Claude gibi her oturum başında (REPL açılışında arka planda, `sync_all`) ve her
`marketplace update` sonrasında (CLI, REPL, masaüstü) çalıştırır. Yerinde yüklenen (#403)
eklentinin klasörü yeni girdinin kaynağına taşınır.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from ..config import plugin_store
from ..config.plugin_scopes import SCOPE_LOCAL, SCOPE_PROJECT, scope_values, write_enabled
from ..config.plugin_store import PluginRecord, load_state, plugins_dir
from ..core.plugin_marketplace import Marketplace

RENAMED = 'Renamed to "{new}" in the "{market}" marketplace'
REMOVED_RENAME = 'Removed from the "{market}" marketplace'
REMOVED_FORCED = '"{name}": Removed from marketplace'
_MAX_CHAIN = 64


def resolve_rename(name: str, renames: Mapping[str, str], current: set[str]) -> str | None:
    """Zinciri izle: güncel ad, kaldırıldıysa "", eşleme yoksa None."""
    seen: set[str] = set()
    while name in renames and name not in seen and len(seen) < _MAX_CHAIN:
        seen.add(name)
        name = renames[name]
        if not name or name in current:
            return name
    return None  # eşleme yok ya da zincir girdilere ulaşmıyor (validate bunu hata sayar)


def sync_marketplace(
    market: Marketplace,
    *,
    base: Path | None = None,
    project: Path | None = None,
    record_root: Path | None = None,
) -> tuple[str, ...]:
    """Bu pazardan kurulu eklentileri girdiler ve `renames` ile eşle; bildirimleri döndür."""
    from .plugin_toggle import entry_name

    root = base or plugins_dir()
    folder = project or Path.cwd()
    current = {entry.name for entry in market.entries}
    renames = dict(market.renames)
    notices: list[str] = []
    for record in load_state(root).plugins:
        if record.marketplace != market.name or entry_name(record) in current:
            continue
        old = entry_name(record)
        target = resolve_rename(old, renames, current)
        if target:
            moved = _moved_folder(record, market, target, record_root)
            _rename(replace(record, folder=moved), old, target, root, folder)
            notices.append(f"{old}: " + RENAMED.format(new=target, market=market.name))
        elif target == "":
            _drop_scope_keys(f"{old}@{market.name}", old, folder)
            notices.append(f"{old}: " + REMOVED_RENAME.format(market=market.name))
            if market.force_remove_deleted:
                _force_remove(record, root)
        elif market.force_remove_deleted:
            _drop_scope_keys(f"{old}@{market.name}", old, folder)
            _force_remove(record, root)
            notices.append(REMOVED_FORCED.format(name=old))
    return tuple(notices)


def _force_remove(record: PluginRecord, root: Path) -> None:
    """Her kapsamdan kaldır ve "Flagged" olarak işaretle (Claude delisted enforcement)."""
    from .plugin_flagged import flag_plugin
    from .plugin_install import uninstall_plugin

    ident = plugin_store.plugin_id(record)
    uninstall_plugin(ident, base=root, everywhere=True)
    flag_plugin(ident, root)


def _rename(record: PluginRecord, old: str, new: str, root: Path, project: Path) -> None:
    updated = replace(record, source=f"{new}@{record.marketplace}")
    plugin_store.update_state(lambda state: state.with_plugin(updated), root)
    for scope in (SCOPE_PROJECT, SCOPE_LOCAL):
        values = scope_values(scope, project)
        key = f"{old}@{record.marketplace}"
        if key in values:
            write_enabled(scope, key, old, None, project)
            write_enabled(scope, f"{new}@{record.marketplace}", new, values[key], project)


def _moved_folder(
    record: PluginRecord, market: Marketplace, new: str, record_root: Path | None
) -> str:
    """Yerinde yüklenen eklenti: yeni girdinin göreli kaynağı (yoksa eski klasör)."""
    if not record.folder or record_root is None:
        return record.folder
    entry = next((e for e in market.entries if e.name == new), None)
    if entry is None or entry.source.kind != "path":
        return record.folder
    candidate = (record_root / entry.source.location).resolve()
    inside = candidate.is_relative_to(record_root.resolve())
    return str(candidate) if inside and candidate.is_dir() else record.folder


def _drop_scope_keys(key: str, name: str, project: Path) -> None:
    for scope in (SCOPE_PROJECT, SCOPE_LOCAL):
        if key in scope_values(scope, project):
            write_enabled(scope, key, name, None, project)


def sync_by_name(name: str, *, base: Path | None = None) -> tuple[str, ...]:
    """Kayıtlı pazarı diskten oku ve eşle (`plugin marketplace update` sonrası)."""
    from .plugin_install import read_marketplace
    from .plugin_market_source import market_root

    record = load_state(base or plugins_dir()).marketplace(name)
    if record is None:
        return ()
    market = read_marketplace(Path(record.path), source=record.source)
    root = market_root(record.kind, Path(record.path))
    return sync_marketplace(market, base=base, record_root=root)


def sync_all(*, base: Path | None = None) -> tuple[str, ...]:
    """Bütün kayıtlı pazarları eşle (Claude: her oturum başında); bozuk pazar ötekini durdurmaz."""
    import logging

    from ..core.plugins import PluginError
    from .plugin_flagged import expire_seen

    expire_seen(base)  # görülmüş Flagged kayıtları 48 saat sonra düşer
    notices: list[str] = []
    for record in load_state(base or plugins_dir()).marketplaces:
        try:
            notices.extend(sync_by_name(record.name, base=base))
        except (OSError, PluginError) as error:
            logging.getLogger(__name__).warning("pazar '%s' eşlenemedi: %s", record.name, error)
    return tuple(notices)


def start_session_sync() -> None:
    """REPL açılışında arka planda `sync_all`; bildirimler sonraki turda basılır."""
    import threading

    from .plugin_auto_update import push_notice

    def run() -> None:
        for notice in sync_all():
            push_notice(notice)

    threading.Thread(target=run, name="fusion-market-sync", daemon=True).start()

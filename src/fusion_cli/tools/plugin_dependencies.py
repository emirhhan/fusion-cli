"""Eklenti bağımlılıkları: kurulumda kendiliğinden kur ve aç, `prune` ile buda (#389, #380, #397).

Claude Code (plugins-reference "dependencies", plugin-dependencies.md): `plugin.json`
`dependencies` dizisi eklenti adı (`"ad"`, `"ad@pazar"`) ya da `{name, marketplace?, version?}`
nesnesidir. Bağımlı eklenti kurulurken bağımlılıklar da kurulur ve açılır. Başka pazardaki
bağımlılık yalnız kök pazarın `marketplace.json` `allowCrossMarketplaceDependenciesOn` listesi o
pazarı içeriyorsa kurulur; yoksa kurulmaz. Kendiliğinden kurulanlar artık hiçbir eklentiye
gerekmeyince `plugin prune` (`autoremove`) ya da `uninstall --prune` ile kaldırılır.

`{name, version}` aralıkları (`^2.0`, `~2.1.0`…) `plugin_dependency_versions` ile
`<ad>--v<sürüm>` git etiketlerinden çözülür; karşılanamazsa bağımlı eklentinin kurulumu geri alınır.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from ..config import plugin_store
from ..config.plugin_store import PluginRecord, load_state, plugin_folder, plugins_dir
from ..core.plugins import PluginError
from . import plugin_install

_LOG = logging.getLogger(__name__)

ERR_CROSS = (
    'Bağımlılık "{dep}" kurulmadı: "{market}" pazarı "{root}" pazarının '
    "allowCrossMarketplaceDependenciesOn listesinde yok"
)
NOTE_INSTALLED = "Bağımlılık kuruldu: {ident}"
NOTE_ENABLED = "Bağımlılık açıldı: {ident}"
NOTE_FAILED = 'Bağımlılık "{dep}" kurulamadı: {error}'
PRUNED = "Kaldırıldı (artık gerekmeyen bağımlılık): {names}"
WOULD_PRUNE = "Kaldırılacak (artık gerekmeyen bağımlılık): {names} (dry run — nothing removed)"
_MAX_DEPTH = 16


def _dependencies(record: PluginRecord, base: Path) -> tuple[str, ...]:
    from ..config.plugin_scan import scan_plugin

    try:
        return scan_plugin(plugin_folder(record, base), record.name).manifest.dependencies
    except (PluginError, OSError):
        return ()


def _ranges_of(record: PluginRecord, base: Path) -> dict[str, str]:
    """`ad@pazar` → aralık (pazarsız bağımlılık bağımlının pazarına çözülür)."""
    from ..config.plugin_scan import scan_plugin

    try:
        pairs = scan_plugin(plugin_folder(record, base), record.name).manifest.dependency_versions
    except (PluginError, OSError):
        return {}
    return {(d if "@" in d else f"{d}@{record.marketplace}"): r for d, r in pairs}


def _requirements(
    ident: str, record: PluginRecord, base: Path
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Bu bağımlılığı isteyen tüm eklentilerin aralıkları ve adları (Claude: hepsi VE'lenir)."""
    ranges: list[str] = []
    dependents: list[str] = []
    others = [r for r in load_state(base).plugins if r.store_key != record.store_key]
    for owner in (record, *others):
        wanted = _ranges_of(owner, base).get(ident)
        if wanted:
            ranges.append(wanted)
            dependents.append(owner.name)
    return tuple(ranges), tuple(dependents)


def _cross_allowed(root_market: str, market: str, base: Path) -> bool:
    if market == root_market:
        return True
    record = load_state(base).marketplace(root_market)
    if record is None:
        return False
    try:
        catalog = plugin_install.read_marketplace(Path(record.path), source=record.source)
    except PluginError:
        return False
    return market in catalog.cross_dependencies


def install_dependencies(
    record: PluginRecord,
    approve: plugin_install.ApprovalCallback,
    *,
    base: Path | None = None,
    depth: int = 0,
) -> tuple[str, ...]:
    """`record`'un bağımlılıklarını kur/aç (özyinelemeli); kullanıcıya gösterilecek notlar."""
    store = base or plugins_dir()
    notes: list[str] = []
    if depth > _MAX_DEPTH:
        return ()
    for dep in _dependencies(record, store):
        name, _, market = dep.partition("@")
        market = market or record.marketplace
        if not market:
            continue  # pazarsız (doğrudan kaynak) eklentinin bağımlılığı çözülemez
        if not _cross_allowed(record.marketplace, market, store):
            notes.append(ERR_CROSS.format(dep=dep, market=market, root=record.marketplace))
            continue
        ident = f"{name}@{market}"
        ranges, dependents = _requirements(ident, record, store)
        notes.extend(_ensure(ident, approve, store, depth, ranges, dependents))
    return tuple(notes)


def _ensure(
    ident: str,
    approve: plugin_install.ApprovalCallback,
    store: Path,
    depth: int,
    ranges: tuple[str, ...] = (),
    dependents: tuple[str, ...] = (),
) -> list[str]:
    from . import plugin_dependency_versions as versions
    from .plugin_toggle import find_record

    wanted = versions.combined(ident, ranges) if ranges else "*"
    try:
        existing = find_record(load_state(store), ident)
    except PluginError:
        existing = None
    if existing is not None:
        versions.check_installed(ident, existing.version, ranges, wanted)
        if existing.enabled:
            return []
        opened = replace(existing, enabled=True)
        plugin_store.update_state(lambda state: state.with_plugin(opened), store)
        return [NOTE_ENABLED.format(ident=ident)]
    pin = _pin_for(ident, wanted, store)
    try:
        item = plugin_install.install_plugin(ident, approve=approve, base=store, pin=pin)
    except PluginError as error:
        return [NOTE_FAILED.format(dep=ident, error=error)]
    if ranges and pin is None:
        try:
            versions.check_pinned(item.record, ranges, dependents)
        except versions.DependencyVersionError:
            plugin_install.uninstall_plugin(item.record.name, base=store, everywhere=True)
            raise
    marked = replace(item.record, dependency=True, enabled=True)
    plugin_store.update_state(lambda state: state.with_plugin(marked), store)
    return [
        NOTE_INSTALLED.format(ident=ident),
        *install_dependencies(marked, approve, base=store, depth=depth + 1),
    ]


def _pin_for(ident: str, wanted: str, store: Path) -> tuple[str, str] | None:
    """Aralık varsa git deposundaki `<ad>--v<sürüm>` etiketi (yoksa göreli eklentide `None`)."""
    from . import plugin_dependency_versions as versions

    if wanted == "*":
        return None
    try:
        target = versions.pin_target(ident, store)
    except PluginError:
        return None
    if target is None:
        return None
    name, url, relative = target
    found = versions.resolve_pin(name, url, wanted, relative=relative)
    if found is None:
        _LOG.info("%s: aralığa uyan %s--v* etiketi yok; güncel kopya kuruluyor", ident, name)
        return None
    return found.tag, found.sha


def prunable(base: Path | None = None) -> tuple[str, ...]:
    """Kendiliğinden kurulmuş ve artık hiçbir kurulu eklentinin gerektirmediği eklentiler."""
    store = base or plugins_dir()
    records = load_state(store).plugins
    keep: set[str] = set()
    for record in records:
        if record.dependency:
            continue
        keep.update(_closure(record, records, store))
    return tuple(sorted(r.name for r in records if r.dependency and r.name not in keep))


def _closure(record: PluginRecord, records: tuple[PluginRecord, ...], store: Path) -> set[str]:
    seen: set[str] = set()
    queue = [record]
    while queue:
        current = queue.pop()
        for dep in _dependencies(current, store):
            name = dep.partition("@")[0]
            match = next((r for r in records if r.name == name), None)
            if match is not None and match.name not in seen:
                seen.add(match.name)
                queue.append(match)
    return seen


def prune(*, dry_run: bool = False, base: Path | None = None) -> str:
    """`plugin prune`: budanacakları kaldır (ya da listele); Claude metni."""
    from .plugin_listing import prune_text

    names = prunable(base)
    if not names:
        return prune_text(dry_run=dry_run)
    if dry_run:
        return WOULD_PRUNE.format(names=", ".join(names))
    for name in names:
        plugin_install.uninstall_plugin(name, base=base, everywhere=True)
    return PRUNED.format(names=", ".join(names))

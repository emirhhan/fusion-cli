"""`plugin install --scope … --marketplace …` (Claude Code birebir, #376, #379, #381).

Claude `install` eklentiyi pazardan kurar ve seçilen kapsamın ayar dosyasına
`enabledPlugins["ad@pazar"] = true` yazar. Fusion dosyaları tek (user) depoda tutar; project/local
kurulumda user kaydı kapalı başlar, eklenti yalnız o kapsamın dosyasında açılır.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from ..config import plugin_store
from ..config.plugin_scopes import SCOPE_USER, check_scope, scope_values, write_enabled
from ..config.plugin_store import (
    InstalledPlugin,
    PluginRecord,
    inspect_plugin,
    load_state,
    plugin_id,
    plugins_dir,
)
from ..core.plugins import PluginError
from . import plugin_install
from .plugin_toggle import find_record

_LOG = logging.getLogger(__name__)

ERR_MARKET_BARE = "--marketplace yalnız çıplak eklenti adıyla kullanılır (ad@pazar değil): {spec}"
WARN_DIRECT = (
    "Doğrudan kaynaktan kurulum kullanımdan kalktı: Claude Code `install` yalnız eklenmiş bir "
    "pazardan kurar. Kullan: fusion plugin install <ad> --marketplace <kaynak>"
)
ERR_NOT_IN_MARKET = (
    'Eklenti kurulamadı "{spec}": eklenti "{spec}" yapılandırılmış hiçbir pazarda yok. '
    "Yerel klasör için: fusion --plugin-dir <yol>; pazar için: "
    "fusion plugin install <ad> --marketplace <kaynak>"
)
ALREADY = 'Plugin "{ident}" is already installed (scope: {scope})'


@dataclass(frozen=True, slots=True)
class ScopedInstall:
    item: InstalledPlugin
    scope: str
    #: Kurulan/açılan bağımlılıkların notları (#389).
    notes: tuple[str, ...] = ()

    @property
    def ident(self) -> str:
        return plugin_id(self.item.record)


def is_direct_source(spec: str) -> bool:
    """Yerel klasör, https adresi ya da sahip/repo: Claude'da `install` bunları kurmaz."""
    text = spec.strip()
    if text.startswith("https://") or (text and Path(text).expanduser().is_dir()):
        return True
    parts = text.split("/")
    return len(parts) == 2 and all(parts) and "@" not in text


def ensure_marketplace(source: str, base: Path) -> str:
    """Bu kaynaktan pazar eklenmişse adını döndür; değilse önce ekle (ağ yalnız yeni git pazarı)."""
    from .plugin_market_source import parse_market_source

    wanted = parse_market_source(source).record_source
    for record in load_state(base).marketplaces:
        if record.source == wanted:
            return record.name
    return plugin_install.add_marketplace(source, base=base).name


def install_scoped(
    spec: str,
    *,
    approve: plugin_install.ApprovalCallback,
    scope: str = "",
    marketplace: str = "",
    expected_digest: str = "",
    base: Path | None = None,
    root: Path | None = None,
    allow_direct: bool = False,
    accept_command: plugin_install.CommandConsent | None = None,
) -> ScopedInstall:
    """Kur ve kapsama yaz. Zaten kuruluysa `PluginAlreadyInstalledError` (Claude: çıkış 0).

    `allow_direct`: eski `kur` adı doğrudan kaynağı bir sürüm daha kabul eder (#379).
    """
    store = base or plugins_dir()
    project = root or Path.cwd()
    target = check_scope(scope) if scope else SCOPE_USER
    if marketplace:
        if "@" in spec or "/" in spec:
            raise PluginError(ERR_MARKET_BARE.format(spec=spec))
        spec = f"{spec.strip()}@{ensure_marketplace(marketplace, store)}"
    elif is_direct_source(spec):
        if not allow_direct:  # Claude `install`: yalnız eklenmiş pazardan (#379)
            raise PluginError(ERR_NOT_IN_MARKET.format(spec=spec))
        _LOG.warning(WARN_DIRECT)
    try:
        item = plugin_install.install_plugin(
            spec,
            approve=approve,
            base=store,
            expected_digest=expected_digest,
            accept_command=accept_command,
        )
    except plugin_install.PluginAlreadyInstalledError:
        if target == SCOPE_USER:
            if is_direct_source(spec):
                raise  # eski doğrudan kaynak: kayıt adı kaynaktan çıkarılamaz
            return _add_user_scope(spec, store)
        return _add_scope(spec, target, store, project)
    from .plugin_dependencies import install_dependencies

    notes = install_dependencies(item.record, approve, base=store)  # #389
    if target == SCOPE_USER:
        return ScopedInstall(item, SCOPE_USER, notes)
    done = _add_scope(plugin_id(item.record), target, store, project, fresh=True)
    return replace(done, notes=notes)


def scope_key(scope: str, project: Path) -> str:
    """Kayıttaki kapsam girdisi: `user` ya da `<kapsam>:<proje kökü>` (#408)."""
    return SCOPE_USER if scope == SCOPE_USER else f"{scope}:{project.resolve()}"


def _add_user_scope(spec: str, store: Path) -> ScopedInstall:
    """Yalnız project/local'de kurulu eklenti user kapsamına da kurulur; zaten varsa bilgi."""
    record = find_record(load_state(store), spec)
    if SCOPE_USER in record.scopes:
        raise plugin_install.PluginAlreadyInstalledError(
            ALREADY.format(ident=plugin_id(record), scope=SCOPE_USER)
        )
    opened = replace(record, enabled=True, scopes=(SCOPE_USER, *record.scopes))
    plugin_store.update_state(lambda state: state.with_plugin(opened), store)
    return ScopedInstall(inspect_plugin(opened, store), SCOPE_USER)


def _add_scope(
    spec: str, scope: str, store: Path, project: Path, *, fresh: bool = False
) -> ScopedInstall:
    record = find_record(load_state(store), spec)
    ident = plugin_id(record)
    values = scope_values(scope, project)
    if not fresh and (values.get(ident) or values.get(record.name)):
        raise plugin_install.PluginAlreadyInstalledError(ALREADY.format(ident=ident, scope=scope))
    key = scope_key(scope, project)
    if fresh:
        # Yalnız bu kapsamda açık: diğer projelerde (user) kapalı başlar.
        record = replace(record, enabled=False, scopes=(key,))
    elif key not in record.scopes:
        record = replace(record, scopes=(*record.scopes, key))
    updated = record
    plugin_store.update_state(lambda state: state.with_plugin(updated), store)
    write_enabled(scope, ident, record.name, True, project)
    return ScopedInstall(inspect_plugin(replace(record, enabled=True), store), scope)


def uninstall_from_scope(spec: str, scope: str, project: Path | None = None) -> str:
    """`uninstall --scope project|local` (#408): o kapsamın `enabledPlugins` girdisini sil.

    Claude gibi kapsamda kayıt yoksa "kurulu değil" hatası. Kaldırılan kimliği döndürür; kayıt
    başka kapsam kullanmıyorsa kopya/veri/ayar silme `uninstall_plugin`'dedir.
    """
    record = find_record(load_state(), spec)
    drop_scope(record, scope, plugins_dir(), project)
    return plugin_id(record)


def default_scope(record: PluginRecord, project: Path | None = None) -> str:
    """`--scope` verilmeyen kaldırma: user; eklenti yalnız bu projede kuruluysa o kapsam."""
    if SCOPE_USER in record.scopes:
        return SCOPE_USER
    root = project or Path.cwd()
    for scope in ("local", "project"):
        if scope_key(scope, root) in record.scopes:
            return scope
    return SCOPE_USER


def drop_scope(
    record: PluginRecord, scope: str, store: Path, project: Path | None = None
) -> PluginRecord:
    """Kapsamı kayıttan ve (project/local ise) ayar dosyasından düşür; güncel kaydı döndür.

    Dönen kaydın `scopes` alanı boşsa eklenti son kapsamından da kalkmıştır.
    """
    from .plugin_toggle import ERR_UNINSTALL_SCOPE

    root = project or Path.cwd()
    if scope == SCOPE_USER:
        if SCOPE_USER not in record.scopes:
            raise PluginError(ERR_UNINSTALL_SCOPE.format(name=record.name, scope=scope))
        left = tuple(item for item in record.scopes if item != SCOPE_USER)
        updated = replace(record, scopes=left, enabled=False)
    else:
        ident = plugin_id(record)
        values = scope_values(scope, root)
        if ident not in values and record.name not in values:
            raise PluginError(ERR_UNINSTALL_SCOPE.format(name=record.name, scope=scope))
        write_enabled(scope, ident, record.name, None, root)
        key = scope_key(scope, root)
        # Eski (kapsam izlenmeyen) kayıtta proje girdisi yok: paylaşılan kopya kalır.
        updated = replace(record, scopes=tuple(item for item in record.scopes if item != key))
    if updated.scopes:
        plugin_store.update_state(lambda state: state.with_plugin(updated), store)
    return updated

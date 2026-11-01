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
ALREADY = 'Plugin "{ident}" is already installed (scope: {scope})'


@dataclass(frozen=True, slots=True)
class ScopedInstall:
    item: InstalledPlugin
    scope: str

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
) -> ScopedInstall:
    """Kur ve kapsama yaz. Zaten kuruluysa `PluginAlreadyInstalledError` (Claude: çıkış 0)."""
    store = base or plugins_dir()
    project = root or Path.cwd()
    target = check_scope(scope) if scope else SCOPE_USER
    if marketplace:
        if "@" in spec or "/" in spec:
            raise PluginError(ERR_MARKET_BARE.format(spec=spec))
        spec = f"{spec.strip()}@{ensure_marketplace(marketplace, store)}"
    elif is_direct_source(spec):
        _LOG.warning(WARN_DIRECT)
    try:
        item = plugin_install.install_plugin(
            spec, approve=approve, base=store, expected_digest=expected_digest
        )
    except plugin_install.PluginAlreadyInstalledError:
        if target == SCOPE_USER:
            raise
        return _add_scope(spec, target, store, project)
    if target == SCOPE_USER:
        return ScopedInstall(item, SCOPE_USER)
    return _add_scope(plugin_id(item.record), target, store, project, fresh=True)


def _add_scope(
    spec: str, scope: str, store: Path, project: Path, *, fresh: bool = False
) -> ScopedInstall:
    record = find_record(load_state(store), spec)
    ident = plugin_id(record)
    values = scope_values(scope, project)
    if not fresh and (values.get(ident) or values.get(record.name)):
        raise plugin_install.PluginAlreadyInstalledError(ALREADY.format(ident=ident, scope=scope))
    if fresh:
        # Yalnız bu kapsamda açık: diğer projelerde (user) kapalı başlar.
        closed = replace(record, enabled=False)
        plugin_store.update_state(lambda state: state.with_plugin(closed), store)
        record = closed
    write_enabled(scope, ident, record.name, True, project)
    return ScopedInstall(inspect_plugin(replace(record, enabled=True), store), scope)


def uninstall_from_scope(spec: str, scope: str, project: Path | None = None) -> str:
    """`uninstall --scope project|local` (#408): yalnız o kapsamın `enabledPlugins` girdisini sil.

    Claude gibi kapsamda kayıt yoksa "kurulu değil" hatası. Paylaşılan kopya ve user kaydı kalır
    (başka kapsamlar kullanıyor olabilir); kaldırılan kimliği döndürür.
    """
    from .plugin_toggle import ERR_UNINSTALL_SCOPE

    root = project or Path.cwd()
    record = find_record(load_state(), spec)
    ident = plugin_id(record)
    values = scope_values(scope, root)
    if ident not in values and record.name not in values:
        raise PluginError(ERR_UNINSTALL_SCOPE.format(name=spec, scope=scope))
    write_enabled(scope, ident, record.name, None, root)
    return ident

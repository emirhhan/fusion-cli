"""Eklentilerin arka planda otomatik güncellenmesi (Claude Code, #394).

Claude Code (https://code.claude.com/docs/en/plugins/loading.md "When auto-update runs"):
- Etkileşimli oturumda, rastgele en çok on dakikalık gecikmeden sonra auto-update'i açık her
  pazar yenilenir ve ondan kurulan eklentiler diskte güncellenir; açık oturum yüklediği sürümle
  sürer ve `Plugin updated: <ad> · Run /reload-plugins to apply` bildirilir.
- Açık mı: (1) `extraKnownMarketplaces` girdisindeki `autoUpdate`, (2) `known_marketplaces.json`
  girdisindeki `autoUpdate` (Fusion'da yok: `/plugin` Marketplaces anahtarı yok), (3) varsayılan:
  Anthropic'in resmî pazarlarında açık (`knowledge-work-plugins`, `first-party-plugins` kapalı),
  diğerlerinde kapalı.
- `DISABLE_UPDATES=1`, `DISABLE_AUTOUPDATER=1` ya da `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`
  bütün geçişi kapatır; `FORCE_AUTOUPDATE_PLUGINS=1` yeniden açar.

Güvenlik davranışı değişti: Claude'daki gibi otomatik güncelleme ayrıca onay sormaz (yalnız
auto-update'i açık pazarlarda). Fusion bildirimi günlüğe yazar (TUI'ye arka plandan basılmaz).
"""

from __future__ import annotations

import logging
import os
import random
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

from ..config.plugin_store import load_state, plugins_dir, plugins_disabled_by_environment
from ..core.plugins import PluginError
from .plugin_declared import DeclaredMarket, declared_marketplaces

_LOG = logging.getLogger(__name__)

NOTICE = "Plugin updated: {name} · Run /reload-plugins to apply"
#: Varsayılanı açık resmî pazarlar (Claude: knowledge-work-plugins ve first-party-plugins kapalı).
DEFAULT_ON = frozenset(
    {
        "claude-plugins-official",
        "claude-code-plugins",
        "claude-code-marketplace",
        "anthropic-agent-skills",
        "life-sciences",
        "claude-for-legal",
        "claude-for-financial-services",
        "financial-services-plugins",
        "healthcare",
    }
)
DISABLE_ENVS = (
    "DISABLE_UPDATES",
    "DISABLE_AUTOUPDATER",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
)
FORCE_ENV = "FORCE_AUTOUPDATE_PLUGINS"
MAX_DELAY_S = 600.0


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in ("", "0", "false", "no")


def auto_update_disabled() -> bool:
    """Ortam değişkenleri geçişi kapatıyor mu? (`FORCE_AUTOUPDATE_PLUGINS` yeniden açar)"""
    if _truthy(FORCE_ENV):
        return False
    return any(_truthy(name) for name in DISABLE_ENVS)


def is_auto_update(name: str, declared: Mapping[str, DeclaredMarket]) -> bool:
    """Önce bildirimdeki `autoUpdate`, yoksa resmî pazar varsayılanı."""
    item = declared.get(name)
    if item is not None and item.auto_update is not None:
        return item.auto_update
    return name in DEFAULT_ON


def _approve(_preview: object) -> bool:
    return True


def _update_market(market: str, store: Path) -> list[str]:
    from .plugin_toggle import plugins_from_marketplace
    from .plugin_update import update_marketplace, update_plugin

    try:
        update_marketplace(market, base=store)
    except PluginError as error:
        _LOG.warning("marketplace not refreshed (%s): %s", market, error)
        return []
    changed: list[str] = []
    for plugin in plugins_from_marketplace(market, store):
        try:
            result = update_plugin(plugin, approve=_approve, base=store)
        except PluginError as error:
            _LOG.warning("eklenti '%s' otomatik güncellenemedi: %s", plugin, error)
            continue
        if result.changed:
            changed.append(plugin)
    return changed


def auto_update_pass(root: Path | None = None, *, base: Path | None = None) -> tuple[str, ...]:
    """auto-update'i açık pazarları yenile, eklentilerini güncelle; değişen eklentiler."""
    if auto_update_disabled() or plugins_disabled_by_environment():
        return ()
    store = base or plugins_dir()
    declared = declared_marketplaces(root or Path.cwd())
    updated: list[str] = []
    for record in load_state(store).marketplaces:
        if is_auto_update(record.name, declared):
            updated.extend(_update_market(record.name, store))
    for name in updated:
        _LOG.info(NOTICE.format(name=name))
    return tuple(updated)


def start_auto_update(
    root: Path, *, notify: Callable[[str], None] | None = None, delay: float | None = None
) -> threading.Thread | None:
    """Oturum açıldıktan sonra rastgele gecikmeyle (en çok 10 dk) arka planda bir geçiş."""
    if auto_update_disabled():
        return None
    wait = random.uniform(0, MAX_DELAY_S) if delay is None else delay

    def run() -> None:
        threading.Event().wait(wait)
        try:
            names = auto_update_pass(root)
        except (OSError, PluginError) as error:
            _LOG.warning("eklenti otomatik güncellemesi başarısız: %s", error)
            return
        for name in names if notify is not None else ():
            notify(NOTICE.format(name=name))

    worker = threading.Thread(target=run, name="fusion-plugin-autoupdate", daemon=True)
    worker.start()
    return worker

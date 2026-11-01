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
auto-update'i açık pazarlarda). Bildirim günlüğe yazılır ve REPL/TUI'de bir sonraki turda
basılır (`drain_notices`).

Resmî pazar (install.md "Official Anthropic marketplace"): `claude-plugins-official` ilk
etkileşimli oturumda kendiliğinden eklenir. Fusion bunu terminal etkileşimliyse, aynı arka plan
geçişinin başında bir kez yapar (`<eklentiler>/.resmi-pazar`); kullanıcı sonra kaldırırsa yeniden
eklenmez. Ağ kapatma değişkenleri (yukarıdaki) bunu da kapatır.
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
OFFICIAL_NAME = "claude-plugins-official"
OFFICIAL_MARKER = ".resmi-pazar"
_NOTICES: list[str] = []
_NOTICES_LOCK = threading.Lock()
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


def push_notice(text: str) -> None:
    with _NOTICES_LOCK:
        _NOTICES.append(text)


def drain_notices() -> tuple[str, ...]:
    """Arka plandan gelen bildirimler (REPL/TUI bir sonraki turda basar); kuyruk boşalır."""
    with _NOTICES_LOCK:
        found = tuple(_NOTICES)
        _NOTICES.clear()
    return found


def ensure_official_marketplace(*, base: Path | None = None) -> bool:
    """İlk etkileşimli oturumda resmî pazarı bir kez ekle; eklendiyse True."""
    from .plugin_install import add_marketplace
    from .plugin_market_source import OFFICIAL_MARKETPLACE

    store = base or plugins_dir()
    marker = store / OFFICIAL_MARKER
    if auto_update_disabled() or plugins_disabled_by_environment() or marker.exists():
        return False
    if load_state(store).marketplace(OFFICIAL_NAME) is None:
        try:
            add_marketplace(OFFICIAL_MARKETPLACE, base=store)
        except PluginError as error:
            _LOG.warning("resmî pazar eklenemedi (sonraki oturumda yeniden denenir): %s", error)
            return False
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("1\n", encoding="utf-8")
    return True


def start_auto_update(
    root: Path,
    *,
    notify: Callable[[str], None] | None = push_notice,
    delay: float | None = None,
    interactive: bool = False,
) -> threading.Thread | None:
    """Oturum açıldıktan sonra rastgele gecikmeyle (en çok 10 dk) arka planda bir geçiş.

    `interactive` (terminal oturumu): geçişten önce resmî pazar bir kez eklenir.
    """
    if auto_update_disabled():
        return None
    wait = random.uniform(0, MAX_DELAY_S) if delay is None else delay

    def run() -> None:
        try:
            if interactive:
                ensure_official_marketplace()
        except OSError as error:
            _LOG.warning("resmî pazar eklenemedi: %s", error)
        threading.Event().wait(wait)
        try:
            names = auto_update_pass(root)
        except (OSError, PluginError) as error:
            _LOG.warning("eklenti otomatik güncellemesi başarısız: %s", error)
            return
        if notify is None:
            return
        for name in names:
            notify(NOTICE.format(name=name))

    worker = threading.Thread(target=run, name="fusion-plugin-autoupdate", daemon=True)
    worker.start()
    return worker

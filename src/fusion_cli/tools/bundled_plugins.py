"""Pakete gömülü `fusion` pazarı ve isteğe bağlı `fusion-ekip` eklentisi (#25).

Claude Code'un yerleşik ajanları yalnız Explore, Plan, general-purpose, claude,
statusline-setup ve claude-code-guide'dır. Fusion'ın Türkçe ekibi (mimar, kodcu, ...) bu
yüzden yerleşik değil; `fusion eklenti kur fusion-ekip` ile kurulan bir eklentidir ve
Claude'daki gibi `fusion-ekip:<ad>` kimliğiyle gelir.

Geçiş: eklenti kurulu değilken eski yalın rol adı (`--agent kodcu`, `agent: kodcu` ayarı,
kayıtlı oturum ajanı) bir sürüm boyunca kullanımdan kalkmış takma ad olarak gömülü dosyaya
çözülür ve süreçte bir kez uyarılır. Bu roller kataloğa, ajan dizinine ve `/agents`
listesine girmez; model onları görmez.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ..config.paths import bundled_marketplace_dir
from ..config.plugin_store import MarketplaceRecord, PluginState

if TYPE_CHECKING:
    from .capabilities import Capability

_LOG = logging.getLogger(__name__)

#: Gömülü pazarın adı (`fusion-ekip@fusion`).
BUNDLED_MARKETPLACE = "fusion"
#: Türkçe ekip ajanlarını taşıyan eklenti.
TEAM_PLUGIN = "fusion-ekip"
#: Eskiden yerleşik olan, artık `fusion-ekip` eklentisindeki roller.
TEAM_ROLES = frozenset(
    {"mimar", "kodcu", "tasarimci", "testci", "arastirmaci", "tarayici", "gorselci", "yonetmen"}
)

_warned: set[str] = set()


def bundled_marketplace_record(state: PluginState) -> MarketplaceRecord | None:
    """Kullanıcı aynı adla pazar eklemediyse gömülü pazarın örtük kaydı."""
    folder = bundled_marketplace_dir()
    if state.marketplace(BUNDLED_MARKETPLACE) is not None or not folder.is_dir():
        return None
    location = str(folder)
    return MarketplaceRecord(BUNDLED_MARKETPLACE, location, "yerel", location)


def team_role_hint(name: str) -> str:
    """Eski yerleşik rol adı için kurulum ipucu; başka adlarda boş."""
    if name not in TEAM_ROLES:
        return ""
    return (
        f" '{name}' artık yerleşik değil (Claude Code'da yok): `fusion eklenti kur "
        f"{TEAM_PLUGIN}` ile kurulunca {TEAM_PLUGIN}:{name} olarak gelir."
    )


def legacy_team_agent(name: str, convert: Callable[..., Capability]) -> Capability | None:
    """Eklenti kurulu değilken eski rol adını gömülü tanıma çöz (bir sürümlük takma ad)."""
    if name not in TEAM_ROLES:
        return None
    path = bundled_marketplace_dir() / TEAM_PLUGIN / "agents" / f"{name}.md"
    if not path.is_file():
        return None
    if name not in _warned:
        _warned.add(name)
        _LOG.warning(
            "'%s' yerleşik ajanı kullanımdan kalkıyor; `fusion eklenti kur %s` ile kurup "
            "%s:%s adını kullanın",
            name,
            TEAM_PLUGIN,
            TEAM_PLUGIN,
            name,
        )
    return convert(Path(path), "fusion", fallback=name)


def reset_warnings() -> None:
    """Testler için: bir kez uyarı kaydını sıfırla."""
    _warned.clear()

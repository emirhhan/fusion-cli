"""Claude Code'un kendi kurduğu eklentiler (`~/.claude/plugins`) — yalnız etkin olanlar (#377).

Claude Code (https://code.claude.com/docs/en/plugins/loading.md "Find plugins on disk"):
kurulumlar `~/.claude/plugins/installed_plugins.json`'da (`{"version": 2, "plugins":
{"ad@pazar": [{"scope", "installPath", …}]}}`), açık/kapalı bilgisi `enabledPlugins`'te durur;
önbellekteki eski sürümler (`.orphaned_at`), pazar klonlarındaki kurulmamış eklentiler ve
kapalı eklentiler YÜKLENMEZ. Ölçüldü (1 Kasım): Fusion `~/.claude/plugins` altındaki BÜTÜN
SKILL.md'leri öneksiz "claude-plugin" becerisi olarak yüklüyordu.

Burada yalnız kullanıcı kapsamındaki etkin kurulumların beceri/komut/ajanları okunur
(`<eklenti>:<ad>` önekiyle). Kanca ve MCP bileşenleri Claude Code'un kendi oturumunda çalışır;
Fusion bunları başlatmaz (`runtime.claude_hooks` ile aynı ilke).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path

from ..core.plugins import PluginError
from .plugin_scan import PluginLayout, scan_plugin

_LOG = logging.getLogger(__name__)

INSTALLED_FILE = Path(".claude") / "plugins" / "installed_plugins.json"
USER_SETTINGS = Path(".claude") / "settings.json"
ORPHAN_MARKER = ".orphaned_at"
USER_SCOPE = "user"


def _read(path: Path) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        _LOG.warning("Claude eklenti dosyası okunamadı (%s): %s", path, error)
        return {}
    return raw if isinstance(raw, Mapping) else {}


def enabled_map(home: Path) -> dict[str, bool]:
    """Kullanıcı `settings.json`'ındaki `enabledPlugins` (`{"ad@pazar": bool}`)."""
    raw = _read(home / USER_SETTINGS).get("enabledPlugins")
    if not isinstance(raw, Mapping):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, bool)}


def claude_plugin_layouts(home: Path) -> tuple[tuple[str, PluginLayout], ...]:
    """`(ad@pazar, düzen)`: kullanıcı kapsamında kurulu ve kapatılmamış Claude eklentileri."""
    plugins = _read(home / INSTALLED_FILE).get("plugins")
    if not isinstance(plugins, Mapping):
        return ()
    enabled = enabled_map(home)
    found: list[tuple[str, PluginLayout]] = []
    for plugin_id, installs in plugins.items():
        path = _user_install(installs)
        if path is None or (path / ORPHAN_MARKER).exists() or not path.is_dir():
            continue
        try:
            layout = scan_plugin(path, str(plugin_id).split("@", 1)[0])
        except PluginError as error:
            _LOG.warning("Claude eklentisi '%s' okunamadı: %s", plugin_id, error)
            continue
        if enabled.get(str(plugin_id), layout.manifest.default_enabled):
            found.append((str(plugin_id), layout))
    return tuple(found)


def _user_install(installs: object) -> Path | None:
    for item in installs if isinstance(installs, list) else ():
        if isinstance(item, Mapping) and item.get("scope") == USER_SCOPE:
            location = item.get("installPath")
            if isinstance(location, str) and location:
                return Path(location)
    return None

"""Beceri klasörü eklentileri: `~/.claude/skills/<ad>/.claude-plugin/plugin.json` (#401, #380).

Claude Code (`claude plugin init` yardımı ve `plugin list` çıktısı, 2.1.287'de ölçüldü):
`~/.claude/skills/<ad>/` altında `.claude-plugin/plugin.json` bulunan klasör kurulmadan
`<ad>@skills-dir` olarak yüklenir; `plugin list` bunu "Skills-directory plugins
(.claude/skills/*):" bölümünde `Scope: user` ile gösterir; `plugin disable <ad>@skills-dir`
kullanıcı `~/.claude/settings.json` dosyasına `enabledPlugins["<ad>@skills-dir"] = false` yazar.
Kaldırma: klasörü silmek. Klasör kullanıcının kendi yazdığı yerdir: kanca/MCP ayrı onay istemez.

Öncelik (Fusion): oturumluk (`--plugin-dir`) ve kurulu aynı adlı eklenti kazanır.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.plugins import PluginError
from .plugin_scan import scan_plugin
from .plugin_store import STATUS_ACTIVE, InstalledPlugin, PluginRecord

_LOG = logging.getLogger(__name__)

SKILLS_DIR_MARKETPLACE = "skills-dir"
SKILLS_DIR_HEADING = "Skills-directory plugins (.claude/skills/*):"
SKILLS_DIR_SCOPE = "user"
_MANIFEST = Path(".claude-plugin") / "plugin.json"
_SETTINGS = Path(".claude") / "settings.json"

WARN_BROKEN = "~/.claude/skills/{name}: eklenti yüklenmedi: {error}"
ERR_SETTINGS = "~/.claude/settings.json okunamadı: {error}"


def skills_root(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".claude" / "skills"


def is_plugin_folder(folder: Path) -> bool:
    return (folder / _MANIFEST).is_file()


def skills_dir_plugin_of(path: Path, root: Path) -> bool:
    """`path` beceri kökündeki bir eklenti klasörünün içinde mi? (düz beceri sayılmaz)."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return len(relative.parts) > 1 and is_plugin_folder(root / relative.parts[0])


def skills_dir_plugins(home: Path | None = None) -> tuple[InstalledPlugin, ...]:
    """Beceri kökündeki eklenti klasörleri (ada göre sıralı; bozuk olan uyarıyla atlanır)."""
    root = skills_root(home)
    try:
        children = sorted(c for c in root.iterdir() if c.is_dir() and is_plugin_folder(c))
    except OSError:
        return ()
    found: list[InstalledPlugin] = []
    for folder in children:
        try:
            layout = scan_plugin(folder.resolve(), folder.name)
        except (PluginError, OSError) as error:
            _LOG.warning(WARN_BROKEN.format(name=folder.name, error=error))
            continue
        record = PluginRecord(
            name=layout.name,
            version=layout.manifest.version,
            source=str(folder.resolve()),
            kind=SKILLS_DIR_MARKETPLACE,
            marketplace=SKILLS_DIR_MARKETPLACE,
            exec_approved=True,
        )
        found.append(InstalledPlugin(record, layout, STATUS_ACTIVE))
    return tuple(found)


def skills_dir_enabled(item: InstalledPlugin, root: Path, home: Path | None = None) -> bool:
    """Açık: manifest `defaultEnabled`; ayarlardaki `"<ad>@skills-dir"` değeri belirler."""
    from .claude_plugins import enabled_map
    from .plugin_scopes import resolve_enabled

    if item.layout is None:
        return False
    ident = f"{item.record.name}@{SKILLS_DIR_MARKETPLACE}"
    user = enabled_map(home or Path.home()).get(ident, item.layout.manifest.default_enabled)
    return resolve_enabled(ident, ident, user, root).enabled


def find_skills_dir(spec: str, home: Path | None = None) -> InstalledPlugin | None:
    name, _, market = spec.partition("@")
    if market and market != SKILLS_DIR_MARKETPLACE:
        return None
    return next((i for i in skills_dir_plugins(home) if i.record.name == name), None)


def write_user_enabled(ident: str, value: bool, home: Path | None = None) -> Path:
    """Kullanıcı `~/.claude/settings.json` `enabledPlugins[ident] = value` (diğerleri korunur)."""
    from .writer import config_lock

    path = (home or Path.home()) / _SETTINGS
    with config_lock(path):
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError) as error:
            raise PluginError(ERR_SETTINGS.format(error=error)) from error
        if not isinstance(raw, dict):
            raise PluginError(ERR_SETTINGS.format(error="nesne değil"))
        current = raw.get("enabledPlugins")
        enabled = dict(current) if isinstance(current, dict) else {}
        updated = {**raw, "enabledPlugins": {**enabled, ident: value}}
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace_text(path, json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
    return path

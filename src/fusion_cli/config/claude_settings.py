"""Claude Code ayar katmanlarını Claude önceliğiyle oku; tek bir üst düzey değeri döndür.

Sıra Claude Code'daki gibidir (settings#settings-precedence; sonraki öncekini ezer):
`~/.claude/settings.json`, proje `.claude/settings.json`, `.claude/settings.local.json`,
`--settings` ve en üstte yönetilen (managed) ayarlar (`claude_top_layers`). Proje dosyaları
yalnız güvenilen projede okunur. Bozuk dosya yazılımı durdurmaz: uyarı yazılır, dosya atlanır.
`claude_setting`, `worktree.*` (#338, #361) ve diğer tek değer okuyucuları bu tek okuyucuyu
kullanır.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path

from .claude_home import claude_user_dir
from .claude_top_layers import top_layers
from .trust import is_permissions_trusted, is_project_settings_trusted

__all__ = ["claude_setting", "claude_settings_layers"]

_LOG = logging.getLogger(__name__)


def _load(path: Path) -> Mapping[str, object] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        _LOG.warning("Claude ayar dosyası okunamadı; atlandı: %s", path)
        return None
    return raw if isinstance(raw, dict) else None


def claude_settings_layers(
    root: Path, *, home: Path | None = None
) -> list[tuple[Mapping[str, object], Path]]:
    """(içerik, kaynak) çiftleri artan öncelikle: kullanıcı, proje, yerel, --settings, managed."""
    paths = [claude_user_dir(home) / "settings.json"]
    if is_project_settings_trusted(root):
        paths.append(root / ".claude" / "settings.json")
    if is_permissions_trusted(root):
        paths.append(root / ".claude" / "settings.local.json")
    layers = [(data, path) for path in paths if (data := _load(path)) is not None]
    layers.extend((top.data, top.source) for top in top_layers(root))
    return layers


def claude_setting(root: Path, key: str, *, home: Path | None = None) -> object | None:
    """`key` için en yüksek öncelikli katmandaki değer; hiçbir katmanda yoksa `None`."""
    found: object | None = None
    for data, _ in claude_settings_layers(root, home=home):
        if key in data:
            found = data[key]
    return found

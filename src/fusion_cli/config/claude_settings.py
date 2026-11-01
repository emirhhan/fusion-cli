"""Claude Code `settings.json` dosyalarından tek bir üst düzey değeri oku.

Sıra Claude Code'daki gibidir (sonraki öncekini ezer): `~/.claude/settings.json`, proje
`.claude/settings.json`, `.claude/settings.local.json`. Proje dosyaları yalnız güvenilen
projede okunur. Bozuk dosya yazılımı durdurmaz: uyarı yazılır, değer atlanır.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .claude_home import claude_user_dir
from .trust import is_permissions_trusted, is_project_settings_trusted

_LOG = logging.getLogger(__name__)


def claude_setting(root: Path, key: str, *, home: Path | None = None) -> object | None:
    """`key` için en son tanımlanan değer; hiçbir dosyada yoksa `None`."""
    paths = [claude_user_dir(home) / "settings.json"]
    if is_project_settings_trusted(root):
        paths.append(root / ".claude" / "settings.json")
    if is_permissions_trusted(root):
        paths.append(root / ".claude" / "settings.local.json")
    found: object | None = None
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError, json.JSONDecodeError):
            _LOG.warning("Claude ayar dosyası okunamadı; %s atlandı: %s", key, path)
            continue
        if isinstance(raw, dict) and key in raw:
            found = raw[key]
    return found

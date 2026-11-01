"""Claude Code `worktree.baseRef` ayarı (#338) ve ayara göre çalışma ağacı açma.

Claude Code (settings-reference › worktree; worktrees › "Choose the base branch"):
`"fresh"` (varsayılan) uzak varsayılan daldan, `"head"` bulunulan `HEAD`'den dallanır. Ayar
`~/.claude/settings.json`, proje `.claude/settings.json` ve `.claude/settings.local.json`'dan
okunur (sonraki öncekini ezer); proje dosyaları yalnız güvenilen projede okunur. `--worktree`,
`/worktree`, `EnterWorktree` ve alt ajan çalışma ağaçları aynı tabanı kullanır.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..core.worktree import Worktree, enter_worktree, project_root_of, repository_root
from ..core.worktree_fetch import BASE_FRESH, BASE_REFS
from .claude_home import claude_user_dir
from .trust import is_permissions_trusted, is_project_settings_trusted

_LOG = logging.getLogger(__name__)


def worktree_base_mode(root: Path, *, home: Path | None = None) -> str:
    """Geçerli `worktree.baseRef`: `"fresh"` ya da `"head"`."""
    paths = [claude_user_dir(home) / "settings.json"]
    if is_project_settings_trusted(root):
        paths.append(root / ".claude" / "settings.json")
    if is_permissions_trusted(root):
        paths.append(root / ".claude" / "settings.local.json")
    mode = BASE_FRESH
    for path in paths:
        value = _base_ref(path)
        if value in BASE_REFS:
            mode = value
        elif value is not None:
            _LOG.warning("worktree.baseRef geçersiz (fresh|head bekleniyor): %s", path)
    return mode


def _base_ref(path: Path) -> str | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        _LOG.warning("Claude ayar dosyası okunamadı; worktree.baseRef atlandı: %s", path)
        return None
    section = raw.get("worktree") if isinstance(raw, dict) else None
    value = section.get("baseRef") if isinstance(section, dict) else None
    return value if isinstance(value, str) or value is None else str(value)


def enter_configured_worktree(cwd: Path, name: str) -> Worktree:
    """`worktree.baseRef` ayarına göre çalışma ağacını aç ya da yeniden kullan."""
    project = project_root_of(cwd.expanduser().resolve())
    root = repository_root(project) or project
    return enter_worktree(cwd, name, base_mode=worktree_base_mode(root))

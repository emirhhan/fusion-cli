"""Claude Code `worktree.baseRef` ayarı (#338) ve ayara göre çalışma ağacı açma.

Claude Code (settings-reference › worktree; worktrees › "Choose the base branch"):
`"fresh"` (varsayılan) uzak varsayılan daldan, `"head"` bulunulan `HEAD`'den dallanır. Ayar
Claude katmanlarından okunur (`claude_settings_layers`: kullanıcı, proje, yerel, --settings,
managed; sonraki öncekini ezer); proje dosyaları yalnız güvenilen projede okunur. `--worktree`,
`/worktree`, `EnterWorktree` ve alt ajan çalışma ağaçları aynı tabanı kullanır.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

from ..core.worktree import (
    Worktree,
    WorktreeHookCalls,
    enter_worktree,
    project_root_of,
    repository_root,
)
from ..core.worktree_fetch import BASE_FRESH, BASE_REFS
from ..core.worktree_layout import WorktreeLayout
from .claude_settings import claude_settings_layers

_LOG = logging.getLogger(__name__)


def _worktree_sections(root: Path, home: Path | None) -> list[tuple[Mapping[str, object], Path]]:
    """Katmanlardaki `worktree` bölümleri Claude önceliğiyle (managed en üstte)."""
    sections = []
    for data, path in claude_settings_layers(root, home=home):
        section = data.get("worktree")
        if isinstance(section, Mapping):
            sections.append((section, path))
    return sections


def worktree_base_mode(root: Path, *, home: Path | None = None) -> str:
    """Geçerli `worktree.baseRef`: `"fresh"` ya da `"head"`."""
    mode = BASE_FRESH
    for section, path in _worktree_sections(root, home):
        value = section.get("baseRef")
        if value in BASE_REFS:
            mode = str(value)
        elif value is not None:
            _LOG.warning("worktree.baseRef geçersiz (fresh|head bekleniyor): %s", path)
    return mode


def _string_list(section: Mapping[str, object], path: Path, key: str) -> list[str]:
    value = section.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _LOG.warning("worktree.%s metin listesi olmalı; atlandı: %s", key, path)
        return []
    return value


def worktree_layout(root: Path, *, home: Path | None = None) -> WorktreeLayout:
    """`worktree.symlinkDirectories` ve `worktree.sparsePaths` (#361; listeler birleşir)."""
    sections = _worktree_sections(root, home)
    links = [
        item for sec, path in sections for item in _string_list(sec, path, "symlinkDirectories")
    ]
    sparse = [item for sec, path in sections for item in _string_list(sec, path, "sparsePaths")]
    return WorktreeLayout(tuple(dict.fromkeys(links)), tuple(dict.fromkeys(sparse)))


def enter_configured_worktree(
    cwd: Path, name: str, *, hooks: WorktreeHookCalls | None = None
) -> Worktree:
    """`worktree.*` ayarlarına göre çalışma ağacını aç ya da yeniden kullan.

    `hooks`: `WorktreeCreate`/`WorktreeRemove` kancaları (#90); tanımlıysa ağacı kanca kurar.
    """
    project = project_root_of(cwd.expanduser().resolve())
    root = repository_root(project) or project
    return enter_worktree(
        cwd,
        name,
        base_mode=worktree_base_mode(root),
        layout=worktree_layout(root),
        hooks=hooks,
    )

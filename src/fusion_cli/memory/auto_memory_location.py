"""Otomatik belleğin Claude Code konumu, adı ve ayarları (#153).

Belge (code.claude.com/docs/en/memory, "Auto memory"): bellek
`~/.claude/projects/<project>/memory/MEMORY.md` ve konu dosyalarıdır; `<project>` git
deposundan türer (aynı deponun worktree'leri ve alt dizinleri tek belleği paylaşır).
`autoMemoryEnabled` (settings.json) ve `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` aç/kapa;
`autoMemoryDirectory` konumu değiştirir (proje settings.json'ı bu anahtarı veremez: depo
belleği başka yere yönlendiremesin). Fusion'ın eski `runtime.auto_memory` /
`runtime.auto_memory_dir` ayarları ve `<bellek>/projeler/<slug>/bellek/BELLEK.md` dizini bir
sürüm boyunca okunur: yeni dizin yoksa bir kez kopyalanır (eski kayıt silinmez).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

_LOG = logging.getLogger(__name__)
_WARNED: set[str] = set()

INDEX_FILE = "MEMORY.md"
LEGACY_INDEX_FILE = "BELLEK.md"
DISABLE_ENV = "CLAUDE_CODE_DISABLE_AUTO_MEMORY"
#: Testler gerçek `~/.claude`'a yazmasın diye ev dizini değiştirilebilir.
HOME_ENV = "FUSION_CLAUDE_HOME"
#: `autoMemoryDirectory` kabul edilen katmanlar (proje katmanı hariç).
_DIRECTORY_ORDER = ("managed", "local", "user")
_DIRECTORY_LAYERS = frozenset(_DIRECTORY_ORDER)


def claude_home() -> Path:
    override = os.environ.get(HOME_ENV, "").strip()
    return Path(override).expanduser() if override else Path.home()


def repository_root(root: Path) -> Path:
    """Git deposunun ana kökü (worktree ise ana deponun kökü); depo yoksa `root`."""
    start = root.resolve()
    for folder in (start, *start.parents):
        marker = folder / ".git"
        if marker.is_dir():
            return folder
        if marker.is_file():
            return _main_repository(marker) or folder
    return start


def _main_repository(marker: Path) -> Path | None:
    try:
        text = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    gitdir = Path(text.removeprefix("gitdir:").strip())
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return gitdir.parent.parent.parent
    return None


def project_key(root: Path) -> str:
    """Claude Code proje dizini adı: yolun harf-rakam dışı her karakteri `-`."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(repository_root(root)))


def default_directory(root: Path, home: Path | None = None) -> Path:
    base = home if home is not None else claude_home()
    return base / ".claude" / "projects" / project_key(root) / "memory"


def configured_directory(root: Path, home: Path | None = None) -> Path | None:
    """settings.json `autoMemoryDirectory` (proje katmanı hariç); yoksa None."""
    from ..config import claude_settings

    base = home if home is not None else claude_home()
    values = {
        item.layer: item.value
        for item in claude_settings.setting_values(root, base, "autoMemoryDirectory")
        if item.layer in _DIRECTORY_LAYERS
    }
    for layer in _DIRECTORY_ORDER:
        value = values.get(layer)
        if isinstance(value, str) and value.strip():
            return Path(value.strip()).expanduser()
    return None


def enabled(root: Path, legacy: bool, home: Path | None = None) -> bool:
    """Ortam değişkeni > settings.json `autoMemoryEnabled` > eski `runtime.auto_memory`."""
    if os.environ.get(DISABLE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    from ..config import claude_settings

    base = home if home is not None else claude_home()
    value = claude_settings.effective(root, base, "autoMemoryEnabled", None)
    return value if isinstance(value, bool) else legacy


def warn_legacy(old: str, new: str) -> None:
    """Eski Fusion ayarı bir sürüm okunur; ilk görüldüğünde bir kez uyarılır."""
    if old in _WARNED:
        return
    _WARNED.add(old)
    _LOG.warning("%s kullanımdan kalktı; settings.json %s kullan", old, new)

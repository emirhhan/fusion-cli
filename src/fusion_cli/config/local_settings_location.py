"""`.claude/settings.local.json`'ın yeri — Claude Code ile birebir (#67, #68).

Kaynak:
code.claude.com/docs/en/settings#where-claude-code-keeps-the-local-file-in-a-git-repository ;
code.claude.com/docs/en/permissions#permission-system.

    Depoda         git deposunun kökü; alt dizinde başlatılsa da kökteki dosya okunur/yazılır
    Worktree       ana checkout'un kökü (`.git` dosyası → `gitdir` → `commondir`)
    Alt modül      `commondir` yoksa modülün kendi kökü
    Depo dışı      oturum kökü
    Windows        oturum kökü (Claude depo kökünü kullanmaz)

Git alt süreci çalıştırılmaz: `.git` dosyası ve `commondir` doğrudan okunur.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Kök göreli yerel ayar dosyası (`trust.PROJECT_PERMISSIONS_PATH` ile aynı).
LOCAL_SETTINGS_RELATIVE = Path(".claude") / "settings.local.json"


def local_settings_path(root: Path) -> Path:
    """Bu oturum kökü için yerel ayar dosyasının mutlak yolu."""
    return local_settings_root(root) / LOCAL_SETTINGS_RELATIVE


def local_settings_root(root: Path) -> Path:
    """Yerel ayar dosyasını taşıyan klasör: git kökü, worktree'de ana checkout."""
    if os.name == "nt":
        return root
    from .workspace_trust import git_root

    try:
        repo = git_root(root.resolve())
    except (OSError, RuntimeError):
        return root
    if repo is None:
        return root
    return _main_checkout(repo) or repo


def _main_checkout(repo: Path) -> Path | None:
    """Worktree'nin ana checkout'u; worktree değilse ya da okunamazsa `None`."""
    marker = repo / ".git"
    if not marker.is_file():
        return None
    try:
        first = marker.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, UnicodeDecodeError, IndexError):
        return None
    if not first.startswith("gitdir:"):
        return None
    gitdir = Path(first.removeprefix("gitdir:").strip())
    if not gitdir.is_absolute():
        gitdir = repo / gitdir
    try:
        common = (gitdir / "commondir").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    common_dir = Path(common) if Path(common).is_absolute() else gitdir / common
    try:
        resolved = common_dir.resolve()
    except (OSError, RuntimeError):
        return None
    # Çıplak depoya bağlı worktree'de ana checkout yoktur; worktree kökü kalır.
    if resolved.name != ".git" or not resolved.is_dir():
        return None
    return resolved.parent

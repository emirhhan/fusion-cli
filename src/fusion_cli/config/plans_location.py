"""Plan dosyalarının yeri: Claude Code `plansDirectory` (#354).

Claude Code (settings-reference `plansDirectory`): plan dosyaları varsayılan olarak
`~/.claude/plans` altındadır; `plansDirectory` ile değişir, göreli yol proje köküne göre
çözülür. Fusion'ın eski yeri (`~/.config/fusion-cli/plans`) okuma için yedek olarak bakılır:
kabul bekleyen eski plan kaybolmaz.
"""

from __future__ import annotations

from pathlib import Path

from .claude_home import claude_user_dir
from .claude_settings import claude_setting
from .paths import plans_dir as legacy_plans_dir


def plans_directory(root: Path | None = None) -> Path:
    """Planların yazılacağı dizin."""
    project = root if root is not None else Path.cwd()
    configured = claude_setting(project, "plansDirectory")
    if isinstance(configured, str) and configured.strip():
        path = Path(configured.strip()).expanduser()
        return path if path.is_absolute() else project / path
    return claude_user_dir() / "plans"


def legacy_directory() -> Path:
    """Fusion'ın eski plan dizini (yalnız okuma yedeği)."""
    return legacy_plans_dir()

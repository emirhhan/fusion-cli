"""`.claude/` yazımı için oturumluk onay — Claude Code ile birebir (#82).

Kaynak: code.claude.com/docs/en/permission-modes#protected-paths. Korumalı `.claude`
yazımında kart "Yes, and allow Claude to edit files in this project's .claude folder for this
session" sunar; `~/.claude/` için ayrı bir sürümü vardır. İzin dosya araçlarına (kabuk değil)
ve yalnız o klasöre verilir; öteki korumalı yollar (`.git/`, `.vscode/`…) yine sorulur.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ...tools.write_targets import FILE_WRITE_TOOLS, write_targets
from ...ui import messages

#: Oturum izni anahtarları (`ApprovalMemory` kapsamı).
PROJECT_KEY = "claude-dir:project"
USER_KEY = "claude-dir:user"
_CLAUDE_DIR = ".claude"


def claude_dir_key(tool_name: str, args: Mapping[str, object], root: Path | None) -> str | None:
    """Dosya aracı yalnız projenin ya da evin `.claude/` klasörüne yazıyorsa anahtarı."""
    if root is None or tool_name not in FILE_WRITE_TOOLS:
        return None
    targets = write_targets(tool_name, args)
    keys = {_key_for(raw, root) for raw in targets}
    if len(keys) != 1:
        return None
    return keys.pop()


def _key_for(raw: str, root: Path) -> str | None:
    text = raw.strip().strip("'\"")
    if not text:
        return None
    try:
        path = Path(text).expanduser()
        absolute = (path if path.is_absolute() else root / path).resolve()
        project = (root / _CLAUDE_DIR).resolve()
        user = (Path.home() / _CLAUDE_DIR).resolve()
    except (OSError, RuntimeError):
        return None
    if absolute.is_relative_to(project):
        return PROJECT_KEY
    if absolute.is_relative_to(user):
        return USER_KEY
    return None


def claude_dir_label(key: str | None) -> str | None:
    """Kartta oturum seçeneğinin Claude metni; `.claude/` yazımı değilse `None`."""
    if key == PROJECT_KEY:
        return messages.CLAUDE_DIR_SESSION_PROJECT
    if key == USER_KEY:
        return messages.CLAUDE_DIR_SESSION_USER
    return None

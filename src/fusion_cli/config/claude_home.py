"""Claude Code kullanıcı yapılandırma dizini: `CLAUDE_CONFIG_DIR` ya da `~/.claude`."""

from __future__ import annotations

import os
from pathlib import Path


def claude_user_dir(home: Path | None = None) -> Path:
    """`home` verilirse `<home>/.claude`; verilmezse `CLAUDE_CONFIG_DIR` ya da `~/.claude`."""
    if home is not None:
        return home / ".claude"
    configured = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".claude"

"""`CLAUDE_ENV_FILE` önsözü: kancanın yazdığı dosya her kabuk komutundan önce çalışır.

Claude Code: "Each Bash command runs the file's contents as shell code before the command
itself" — `export PATH="$PATH:./node_modules/.bin"` gibi satırlar kabukta değerlendirilir.
Dosyalar SessionStart/CwdChanged kancalarına `CLAUDE_ENV_FILE` olarak verilir
(`engines/hooks/session.py`); yol `ToolContext.shell_env_files` ile gelir.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from ..core.tools import ToolContext


def env_files(context: ToolContext) -> tuple[Path, ...]:
    """Var olan ve boş olmayan ortam dosyaları (eski ToolContext'te alan yoksa boş)."""
    paths = getattr(context, "shell_env_files", None) or ()
    found: list[Path] = []
    for path in paths:
        try:
            if path.is_file() and path.stat().st_size > 0:
                found.append(path)
        except OSError:
            continue
    return tuple(found)


def with_env_prelude(command: str, context: ToolContext) -> str:
    """Komutun önüne ortam dosyalarını `.` ile ekle; dosya yoksa komut aynen döner."""
    files = env_files(context)
    if not files:
        return command
    prelude = "".join(f". {shlex.quote(str(path))}\n" for path in files)
    return prelude + command

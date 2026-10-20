"""Proje yazmak için gereken geliştirici araçlarını algıla.

Fusion bu araçları KENDİ BAŞINA kurmaz: yalnız bu bilgisayarda var olup
olmadığına bakar ve eksikse resmî indirme sayfasını gösterir; kurulumu
kullanıcı yapar. Finder'dan açılan uygulamanın PATH'i dardır, bu yüzden
yaygın kurulum klasörleri de aranır.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

_EXTRA_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")
_VERSION_TIMEOUT_SECONDS = 5

CommandFinder = Callable[[str], str | None]
VersionReader = Callable[[str, str], str | None]


@dataclass(frozen=True)
class _Tool:
    id: str
    ad: str
    komutlar: tuple[str, ...]
    surum_bayragi: str
    neden: str
    indirme: str


_TOOLS = (
    _Tool(
        "node",
        "Node.js",
        ("node",),
        "--version",
        "Web ve JavaScript projeleri için gerekir.",
        "https://nodejs.org/en/download",
    ),
    _Tool(
        "python",
        "Python",
        ("python3", "python"),
        "--version",
        "Python projeleri ve betikler için gerekir.",
        "https://www.python.org/downloads/",
    ),
    _Tool(
        "git",
        "Git",
        ("git",),
        "--version",
        "Değişiklikleri kaydetmek ve geri almak için gerekir.",
        "https://git-scm.com/downloads",
    ),
)


def _find(command: str) -> str | None:
    search = os.pathsep.join([os.environ.get("PATH", ""), *_EXTRA_DIRS])
    return shutil.which(command, path=search)


def _read_version(path: str, flag: str) -> str | None:
    try:
        done = subprocess.run(
            [path, flag],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (done.stdout or done.stderr).strip()
    return text.splitlines()[0] if text else None


def detect_dev_tools(
    *, find_command: CommandFinder = _find, read_version: VersionReader = _read_version
) -> dict[str, object]:
    """Her araç için `kurulu` ve (varsa) sürüm; eksikse indirme bağlantısı."""
    rows: list[dict[str, object]] = []
    for tool in _TOOLS:
        path = next((found for name in tool.komutlar if (found := find_command(name))), None)
        rows.append(
            {
                "id": tool.id,
                "ad": tool.ad,
                "neden": tool.neden,
                "kurulu": path is not None,
                "surum": read_version(path, tool.surum_bayragi) if path else None,
                "indirme": tool.indirme,
            }
        )
    return {"ok": True, "araclar": rows}

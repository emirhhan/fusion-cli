"""Yerel ayar dosyasını genel git dışlamasına ekleme — Claude Code ile birebir (#67).

Kaynak: code.claude.com/docs/en/settings (settings.local.json): "When Claude Code first
writes .claude/settings.local.json in a git repo that doesn't already ignore it, it adds the
file to your global git excludes". Elle oluşturulan dosyaya dokunulmaz (çağıran yalnız
Fusion dosyayı İLK KEZ oluşturduğunda çağırır).

Dışlama dosyası git'in kendi kuralıyla seçilir: `core.excludesFile`, yoksa
`$XDG_CONFIG_HOME/git/ignore` (ya da `~/.config/git/ignore`). Git yoksa ya da yazılamıyorsa
kural yazımı düşmez; durum günlüğe yazılır.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from .local_settings_location import LOCAL_SETTINGS_RELATIVE

_logger = logging.getLogger(__name__)

#: Genel dışlama dosyasına eklenen satır: Claude Code'un yazdığıyla aynı (bu makinedeki
#: `~/.config/git/ignore`'da gözlendi, 1 Kasım).
IGNORE_LINE = f"**/{LOCAL_SETTINGS_RELATIVE.as_posix()}"
#: Git çağrısı için üst sınır (saniye).
_GIT_TIMEOUT_SECONDS = 5


def ensure_globally_ignored(repo: Path) -> bool:
    """Depo dosyayı zaten dışlamıyorsa genel dışlamaya ekle; eklendiyse `True`."""
    if not (repo / ".git").exists():
        return False
    ignored = _git(repo, "check-ignore", "-q", LOCAL_SETTINGS_RELATIVE.as_posix())
    if ignored is None or ignored.returncode == 0:
        return False
    target = global_excludes_file(repo)
    if target is None:
        return False
    try:
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        if IGNORE_LINE in existing.splitlines():
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(f"{prefix}{IGNORE_LINE}\n")
    except (OSError, UnicodeDecodeError) as error:
        _logger.warning("Genel git dışlama dosyası yazılamadı (%s): %s", target, error)
        return False
    return True


def global_excludes_file(repo: Path) -> Path | None:
    """Git'in genel dışlama dosyası; git çalışmıyorsa `None`."""
    configured = _git(repo, "config", "--global", "--get", "core.excludesFile")
    if configured is None:
        return None
    value = configured.stdout.strip()
    if configured.returncode == 0 and value:
        return Path(value).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "git" / "ignore"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        _logger.info("git çalıştırılamadı (%s): %s", " ".join(args), error)
        return None

"""Alt ajan kalıcı belleği Claude Code yollarında (#24, P-055).

Claude Code: `user` → `~/.claude/agent-memory/<ad>/`, `project` → `.claude/agent-memory/<ad>/`,
`local` → `.claude/agent-memory-local/<ad>/`; indeks dosyası `MEMORY.md`. Fusion'ın eski
yerleri (`<bellek>/ajan-bellek`, `.fusion/ajan-bellek`, `.fusion/ajan-bellek-yerel`, indeks
`BELLEK.md`) bir sürüm boyunca okunur: yeni dizin yoksa düzenli dosyalar bir kez kopyalanır
(sembolik bağ izlenmez), eski kayıt silinmez.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from ..config.models import Config

_LOG = logging.getLogger(__name__)

AGENT_INDEX_FILE = "MEMORY.md"
LEGACY_INDEX_FILE = "BELLEK.md"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _dir_name(agent: str) -> str:
    from .plain_memory import topic_slug

    return agent if _SAFE_NAME.match(agent) else topic_slug(agent)


def agent_memory_dir(
    config: Config, root: Path, agent: str, scope: str, *, home: Path | None = None
) -> Path | None:
    """Claude Code ajan belleği dizini; tanınmayan kapsam None."""
    del config  # imza eski çağıranlarla uyumlu kalır
    name = _dir_name(agent)
    if scope == "user":
        return (home if home is not None else Path.home()) / ".claude" / "agent-memory" / name
    if scope == "project":
        return root / ".claude" / "agent-memory" / name
    if scope == "local":
        return root / ".claude" / "agent-memory-local" / name
    return None


def legacy_agent_memory_dir(config: Config, root: Path, agent: str, scope: str) -> Path | None:
    """Fusion'ın eski ajan belleği dizini (yalnız taşıma için okunur)."""
    from .plain_memory import topic_slug

    slug = topic_slug(agent)
    if scope == "user":
        return config.memory_dir / "ajan-bellek" / slug
    if scope == "project":
        return root / ".fusion" / "ajan-bellek" / slug
    if scope == "local":
        return root / ".fusion" / "ajan-bellek-yerel" / slug
    return None


def migrate_legacy(legacy: Path | None, target: Path) -> None:
    """Yeni dizin yoksa eski dizindeki DÜZENLİ dosyaları kopyala; bağları izleme."""
    if legacy is None or target.exists() or legacy.is_symlink() or not legacy.is_dir():
        return
    try:
        base = legacy.resolve()
        for source in sorted(legacy.rglob("*")):
            if source.is_symlink() or not source.is_file():
                continue
            if not source.resolve().is_relative_to(base):
                continue
            relative = source.relative_to(legacy)
            if relative == Path(LEGACY_INDEX_FILE):
                relative = Path(AGENT_INDEX_FILE)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    except OSError:
        _LOG.warning("eski ajan belleği taşınamadı", extra={"kaynak": str(legacy)})

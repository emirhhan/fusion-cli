"""Beceri çağrı sayıları: liste bütçesi aşılınca az çağrılanın açıklaması önce düşer (#156).

Belge (code.claude.com/docs/en/skills, "Skill descriptions are cut short"): bütçe dolunca
en az çağrılan becerilerin açıklamaları önce düşer, adlar her zaman kalır. Fusion çağrıyı
(kullanıcının `/ad`'ı ve modelin `Skill` aracı) `memory_dir/beceri_cagrilari.json`'da sayar;
istem metni yazılmaz, yalnız ad → sayı.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ...core.atomic_file import atomic_replace_text

USAGE_FILE = "beceri_cagrilari.json"

_LOG = logging.getLogger(__name__)


def _path(memory_dir: Path) -> Path:
    return memory_dir / USAGE_FILE


def load_counts(memory_dir: Path | None) -> dict[str, int]:
    """Ad (küçük harf) → çağrı sayısı; dosya yoksa ya da bozuksa boş."""
    if memory_dir is None:
        return {}
    try:
        raw = json.loads(_path(memory_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): int(value)
        for key, value in raw.items()
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    }


def record_invocation(memory_dir: Path | None, name: str) -> None:
    """Bir çağrıyı say; yazılamazsa çağrı bozulmaz, yalnız loglanır."""
    key = name.strip().lower()
    if memory_dir is None or not key:
        return
    counts = load_counts(memory_dir)
    updated = {**counts, key: counts.get(key, 0) + 1}
    try:
        memory_dir.mkdir(parents=True, exist_ok=True)
        atomic_replace_text(_path(memory_dir), json.dumps(updated, ensure_ascii=False))
    except OSError:
        _LOG.warning("beceri çağrı sayısı yazılamadı: %s", _path(memory_dir), exc_info=True)

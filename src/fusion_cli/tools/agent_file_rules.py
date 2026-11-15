"""Claude Code'un sessizce atladığı ajan dosyaları (#19, #41).

Belge (sub-agents › Write subagent files): `name` yoksa dosya belge sayılır; açılış `---`
ilk satırda değilse frontmatter yoktur; `name` `-` ile başlıyor, `:` içeriyor ya da 256
karakteri aşıyorsa, `description` yoksa dosya atlanır. Atlama oturumda raporlanmaz; yalnız
hata ayıklama günlüğüne düşer.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

_LOG = logging.getLogger(__name__)
_MAX_NAME = 256


def agent_file_problem(raw: str, fields: Mapping[str, object]) -> str:
    """Dosya atlanacaksa nedenini, geçerliyse boş metni döndür."""
    if not raw.removeprefix("﻿").startswith("---"):
        return "açılış --- ilk satırda değil"
    name = str(fields.get("name") or "").strip()
    if not name:
        return "name alanı yok"
    if name.startswith("-") or ":" in name or len(name) > _MAX_NAME:
        return "name geçersiz"
    if not str(fields.get("description") or "").strip():
        return "description alanı yok"
    return ""


def log_skipped(path: Path, reason: str) -> None:
    _LOG.debug("ajan dosyası atlandı", extra={"yol": str(path), "neden": reason})

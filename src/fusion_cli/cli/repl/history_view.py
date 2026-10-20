"""Açılışta basılan son oturum listesi.

Amaç geçmişi HATIRLATMAKTIR, tam bir tarayıcı sunmak değil: tam liste
`/resume<kaynak>` ile açılır. Oturum yoksa hiçbir şey basılmaz — boş bir başlık
gürültüdür ve açılış ekranını uzatır.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ...history import recent_sessions
from ...ui import messages


def render_recent(home: Path, root: Path) -> str:
    """Son oturumları tek bir metin bloğu olarak döndür. Yoksa boş dizge."""
    refs = recent_sessions(home, root)
    if not refs:
        return ""
    lines = [messages.HISTORY_RECENT_TITLE]
    for ref in refs:
        when = (
            datetime.fromtimestamp(ref.updated_at).strftime("%d/%m %H:%M") if ref.updated_at else ""
        )
        lines.append(f"  {ref.source:<7} {when:<12} {ref.title}")
    return "\n".join(lines)

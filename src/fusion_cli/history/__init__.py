"""Başka araçların oturum geçmişini okuyan arayüzden bağımsız çekirdek.

CLI komutları, ajan aracı ve ileride masaüstü uygulaması aynı bu katmanı çağırır;
davranış hiçbir sunum yüzeyine gömülmez.
"""

from __future__ import annotations

from .models import SessionRef, Turn
from .registry import available_sources, recent_sessions, source_by_name

__all__ = [
    "SessionRef",
    "Turn",
    "available_sources",
    "recent_sessions",
    "source_by_name",
]

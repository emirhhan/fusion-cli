"""Başka araçların oturum geçmişini okuyan arayüzden bağımsız çekirdek.

CLI komutları, ajan aracı ve ileride masaüstü uygulaması aynı bu katmanı çağırır;
davranış hiçbir sunum yüzeyine gömülmez.
"""

from __future__ import annotations

from .digest import build_digest
from .models import SessionRef, Turn
from .registry import available_sources, recent_sessions, source_by_name
from .search import SearchResult, SessionMatch, search_sessions

__all__ = [
    "SearchResult",
    "SessionMatch",
    "SessionRef",
    "Turn",
    "available_sources",
    "build_digest",
    "recent_sessions",
    "search_sessions",
    "source_by_name",
]

"""Kurulu geçmiş kaynaklarını bulur ve ada göre çözer.

Bir kaynak yalnızca izi varsa etkinleşir. Tespit tek bir varlık kontrolüdür:
dosya açılmaz, sorgu çalıştırılmaz. Kurulmamış bir aracın komutu HİÇ var olmaz —
gri gösterilmez, "kurulu değil" demez; kayıt defterine hiç girmez.
"""

from __future__ import annotations

from pathlib import Path

from .claude_source import ClaudeSource
from .codex_source import CodexSource
from .hermes_source import HermesSource
from .models import HistorySource, SessionRef

#: Açılış listesinde gösterilecek en fazla oturum.
RECENT_LIMIT = 5


def all_sources(home: Path) -> tuple[HistorySource, ...]:
    """Bilinen tüm kaynaklar, kurulu olsun olmasın."""
    return (ClaudeSource(home), CodexSource(home), HermesSource(home))


def available_sources(home: Path) -> tuple[HistorySource, ...]:
    """Yalnızca makinede izi bulunan kaynaklar."""
    return tuple(source for source in all_sources(home) if source.is_installed())


def source_by_name(home: Path, name: str) -> HistorySource | None:
    """Kurulu kaynağı adıyla çöz. Kurulu değilse `None`."""
    wanted = name.strip().lower()
    return next((s for s in available_sources(home) if s.name == wanted), None)


def recent_sessions(home: Path, root: Path, limit: int = RECENT_LIMIT) -> tuple[SessionRef, ...]:
    """Tüm kurulu kaynaklardan en son oturumlar, karışık ve zamana göre sıralı.

    Her kaynaktan `limit` kadar istenir — kaynak sayısı kadar DEĞİL, çünkü
    harmanlama sonrası yine `limit`'e kırpılacaktır. Bir kaynaktan daha AZ
    istemek yanlış sonuç verir: o kaynağın en yeni oturumlarından biri,
    harmanlanmış listede yer almayı hak edebilecekken dışarıda kalabilir.
    Her kaynağın kendi `list` uygulaması, bu `limit`'i gereksiz ayrıştırmayı
    önlemek için kullanır (bkz. `HistorySource.list` sözleşmesi).
    """
    collected: list[SessionRef] = []
    for source in available_sources(home):
        collected.extend(source.list(root, limit=limit))
    collected.sort(key=lambda ref: ref.updated_at, reverse=True)
    return tuple(collected[:limit])

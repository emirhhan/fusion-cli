"""`--resume <kimlik|ad>` çözümü Claude Code kurallarıyla (#203).

- Kimlik: önce bu proje (ve çalışma ağaçları), sonra makinedeki öteki projeler; öteki
  projelerde yalnız TEK bir projede bulunursa çözülür (elle kopyalanmış eş "bulunamadı").
- Ad: tam eşleşme (büyük/küçük harf duyarlı); tek sohbetse doğrudan, birden çoksa belirsiz
  (`fusion --resume <ad>` seçiciyi o adla süzerek açar, `/resume <ad>` hata verir).
- Fusion'ın eski davranışı (büyük/küçük duyarsız ad, 6+ karakterlik kimlik öneki) tam eşleşme
  yoksa bir sürüm boyunca kullanımdan kalkmış yedek olarak kalır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .transcript_store import (
    ConversationRef,
    find_conversation,
    list_conversations,
    transcript_events_path,
)


@dataclass(frozen=True, slots=True)
class Resolution:
    ref: ConversationRef | None = None
    #: Sohbet başka projedeyse onun transcript dosyası.
    events_path: Path | None = None
    #: Ad birden çok sohbetle tam eşleşti.
    ambiguous: tuple[ConversationRef, ...] = ()


def _other_projects(base_dir: Path, root: Path) -> list[Path]:
    current = transcript_events_path(base_dir, root)
    folder = base_dir.expanduser().resolve() / "transcripts"
    try:
        files = sorted(folder.glob("*/events.jsonl"))
    except OSError:
        return []
    return [path for path in files if path != current]


def resolve_path(base_dir: Path, root: Path, query: str) -> Resolution | None:
    """Mutlak `.jsonl` transcript yolu (#188): tek sohbetse o, çoksa belirsiz; yol değilse None."""
    path = Path(query.strip()).expanduser()
    if path.suffix != ".jsonl" or not path.is_absolute():
        return None
    if not path.is_file():
        return Resolution()
    refs = tuple(list_conversations(base_dir, root, events_path=path.resolve()))
    if len(refs) == 1:
        return Resolution(refs[0], events_path=path.resolve())
    return Resolution(ambiguous=refs, events_path=path.resolve()) if refs else Resolution()


def resolve(base_dir: Path, root: Path, query: str) -> Resolution:
    wanted = query.strip()
    if not wanted:
        return Resolution()
    by_path = resolve_path(base_dir, root, wanted)
    if by_path is not None:
        return by_path
    refs = list_conversations(base_dir, root)
    by_id = next((ref for ref in refs if ref.conversation_id == wanted), None)
    if by_id is not None:
        return Resolution(by_id)
    named = tuple(ref for ref in refs if ref.name and ref.name == wanted)
    if len(named) == 1:
        return Resolution(named[0])
    if len(named) > 1:
        return Resolution(ambiguous=named)
    elsewhere = [
        (path, ref)
        for path in _other_projects(base_dir, root)
        for ref in list_conversations(base_dir, root, events_path=path)
        if ref.conversation_id == wanted and ref.message_count > 0
    ]
    if len(elsewhere) == 1:
        path, ref = elsewhere[0]
        return Resolution(ref, events_path=path)
    if elsewhere:
        return Resolution()
    return Resolution(find_conversation(base_dir, root, wanted))

"""Pure local MCP reference syntax and expansion result; no SDK or transport imports."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

SLASH_PREFIX = "mcp__"
_MENTION = re.compile(r"(?:(?<=\s)|^)@([A-Za-z0-9_-]{2,}):(\S+)")
_TRAILING_PUNCT = ".,;!?)»\"'"


@dataclass(frozen=True, slots=True)
class McpExpansion:
    """Görev metninin MCP başvuruları çözülmüş hâli."""

    task: str
    context: str = ""
    notes: tuple[str, ...] = ()
    #: Doluysa tur KOŞMAZ: istem alınamadı (model ham `/mcp__…` metniyle çalışmasın).
    error: str = ""
    resources: tuple[str, ...] = field(default_factory=tuple)
    #: Kullanıcıya uyarı olarak gösterilecekler (bağlı olmayan sunucu, okunamayan kaynak).
    warnings: tuple[str, ...] = ()


def parse_prompt_call(task: str) -> tuple[str, str] | None:
    """`/mcp__s__p argümanlar` → (`mcp__s__p`, argümanlar); başka metinde None."""
    stripped = task.strip()
    if not stripped.startswith("/" + SLASH_PREFIX):
        return None
    head, _, rest = stripped[1:].partition(" ")
    return head, rest.strip()


def resource_mentions(task: str, servers: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Görevdeki `@sunucu:uri` anmaları; yalnız tanımlı sunucu adlarıyla, tekrar elenir."""
    known = {name.lower(): name for name in servers}
    found: list[tuple[str, str]] = []
    for match in _MENTION.finditer(task):
        server = known.get(match.group(1).lower())
        uri = match.group(2).rstrip(_TRAILING_PUNCT)
        if server is None or not uri or (server, uri) in found:
            continue
        found.append((server, uri))
    return tuple(found)

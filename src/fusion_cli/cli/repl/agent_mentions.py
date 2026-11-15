"""`@agent-<ad>` ve `@"<ad> (agent)"` anmaları (#26).

Claude Code: anılan alt ajan o turda kesin çalışır; görev metnini model yazar. Fusion anmayı
bağlama bir system-reminder olarak ekler ve modelden `Agent` aracını o tiple çağırmasını ister.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...ui import messages

if TYPE_CHECKING:
    from .state import ReplState

_QUOTED = re.compile(r'@"([^"\n]+?) \(agent\)"')
_PLAIN = re.compile(r"(?:(?<=\s)|^)@agent-([^\s@]+)")
_TRAILING = ".,;!?)»\"'"


def agent_mentions(line: str) -> tuple[str, ...]:
    """Satırdaki ajan anmalarının adları (sıra korunur, tekrar elenir)."""
    names = [match.group(1).strip() for match in _QUOTED.finditer(line)]
    names.extend(match.group(1).rstrip(_TRAILING) for match in _PLAIN.finditer(line))
    return tuple(dict.fromkeys(name for name in names if name))


def without_agent_mentions(line: str) -> str:
    """Dosya anması taramasından önce ajan anmalarını çıkar."""
    return _PLAIN.sub(" ", _QUOTED.sub(" ", line))


def resolve_agent_mentions(line: str, state: ReplState) -> tuple[list[str], list[str]]:
    """Ajan anmalarını bağlam bloğuna ve kullanıcı notuna çevir."""
    blocks: list[str] = []
    notes: list[str] = []
    library = state.capabilities
    for name in agent_mentions(line):
        agent = library.get_agent(name) if library is not None else None
        if agent is None:
            notes.append(messages.AGENT_MENTION_UNKNOWN.format(name=name))
            continue
        blocks.append(messages.AGENT_MENTION_BLOCK.format(name=agent.name))
        notes.append(messages.AGENT_MENTION_ADDED.format(name=agent.name))
    return blocks, notes

"""Etkileşimli `--session-id <uuid>` doğrulaması (#204).

Claude Code: `--session-id` sohbete belirli bir UUID verir; kullanılmış kimlik yeniden
açılmaz. `claude "query"` / `claude -r "<oturum>" "query"` konum argümanını kök Typer grubu
`print_argv.ClaudeArgsGroup` gizli `--initial-prompt` seçeneğine çevirir (#276).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from ...core.errors import SessionNotFoundError
from ...ui import messages


def session_id_value(raw: str) -> str:
    """`--session-id` değerini doğrula; Fusion sohbet kimliğine (`session-<hex>`) çevir."""
    try:
        parsed = uuid.UUID(raw.strip())
    except ValueError:
        raise SessionNotFoundError(messages.SESSION_ID_INVALID.format(value=raw)) from None
    return f"session-{parsed.hex}"


def ensure_unused(memory_dir: Path, root: Path, conversation_id: str) -> None:
    """Claude Code: kullanılan bir kimlik `--session-id` ile yeniden açılmaz."""
    from .transcript_store import list_conversations

    if any(ref.conversation_id == conversation_id for ref in list_conversations(memory_dir, root)):
        raise SessionNotFoundError(messages.SESSION_ID_IN_USE.format(value=conversation_id))

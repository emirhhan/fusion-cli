"""`/clear [ad]` (takma adları `/reset`, `/new`): boş bağlamla YENİ sohbet (#185).

Claude Code: `/clear` yeni bir konuşma başlatır; önceki konuşma kayıtlı kalır ve
`/resume` ile geri açılır. Argüman verilirse BIRAKILAN konuşmaya ad olarak yazılır.
Ölçüldü (1 Kasım): Fusion'da `/clear` yalnız ekranı temizliyor, `/reset` geçmişi silip
aynı sohbet kimliğinde kalıyordu; eski mesajlar ayrıca sürdürülemiyordu.

Ekran temizliği Claude'daki gibi Ctrl+L'dedir.
"""

from __future__ import annotations

import time

from ...ui import messages
from . import session_agent
from .session_resume import new_conversation_id
from .state import ReplState
from .transcript_store import TranscriptStore


def clear_command(state: ReplState, argument: str) -> str:
    """Bırakılan sohbete (varsa) ad ver, geçmişi sil ve yeni sohbet kimliğine geç."""
    name = argument.strip()
    previous_id = state.conversation_id
    had_messages = bool(state.history)
    if name:
        TranscriptStore(
            state.config.memory_dir, state.root, conversation_id=previous_id
        ).record_name(name)
    new_id = new_conversation_id()
    # `/resume` ile bu sohbete dönülürse izin kipi geri yüklenmez (Claude Code, #189).
    state.opened_conversations = state.opened_conversations | {previous_id}
    state.conversation_id = new_id
    removed = state.reset_history(session_id=new_id)
    state.conversation_name = ""
    state.last_changes = None
    state.checkpoints.clear()
    # Claude Code (#191): yeni oturumda `cost.total_cost_usd` $0'dan, süre baştan başlar.
    state.cost.reset()
    state.started_at = time.monotonic()
    if had_messages:
        # Claude Code (#200): aynı süreçte `/rewind` menüsü `/resume <kimlik>` satırı sunar.
        state.cleared_session = (previous_id, new_id)
    from . import chrome_cli

    # Claude in Chrome: `/clear` oturumun sekme grubunu sayfalarıyla kapatır (#436).
    chrome_cli.schedule_close_group(getattr(state, "chrome", None), only_empty=False)
    persona = getattr(state, "persona", None)
    if persona is not None:
        # Oturum ajanı (`--agent`) yeni sohbette de geçerlidir; kaydı yeni kimliğe taşınır.
        session_agent.save(state.config.memory_dir, new_id, persona.name)
    if not had_messages:
        return messages.SESSION_CLEARED_EMPTY
    if name:
        return messages.SESSION_CLEARED_NAMED.format(count=removed, name=name)
    return messages.SESSION_CLEARED.format(count=removed)

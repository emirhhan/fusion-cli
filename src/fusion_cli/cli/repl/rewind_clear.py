"""`/clear` öncesi oturuma `/rewind` ile dönüş (#200, Claude Code).

Claude Code "Rewind past a cleared conversation": aynı süreçte `/clear` çalıştıysa geri sarma
menüsünün başında `/resume <session-id> (previous session)` satırı durur; seçilince `/clear`
öncesi konuşma sürdürülür. Satır çıkışa ya da başka bir oturumu sürdürene kadar kalır.
"""

from __future__ import annotations

from ...ui import messages
from ...ui.picker import Choice
from .state import ReplState

#: Seçim değerinin öneki: `resume:<kimlik>`; `/rewind` argümanı olarak da kabul edilir.
RESUME_PREFIX = "resume:"


def previous_session(state: ReplState) -> str:
    """`/clear` ile bırakılan sohbetin kimliği; başka sohbete geçildiyse boş."""
    cleared: tuple[str, str] | None = getattr(state, "cleared_session", None)
    if not cleared or cleared[1] != state.conversation_id:
        return ""
    return cleared[0]


def previous_session_choices(state: ReplState) -> list[Choice]:
    """Menünün başına konacak satır (yoksa boş liste)."""
    previous = previous_session(state)
    if not previous:
        return []
    return [
        Choice(
            f"{RESUME_PREFIX}{previous}",
            messages.REWIND_PREVIOUS_SESSION.format(id=previous),
            messages.REWIND_PREVIOUS_SESSION_HINT,
        )
    ]


def resume_target(argument: str) -> str | None:
    """`/rewind resume:<kimlik>` → kimlik; değilse None."""
    word = argument.strip()
    if not word.startswith(RESUME_PREFIX) or " " in word:
        return None
    return word[len(RESUME_PREFIX) :] or None

"""`/goal` komutu (P-058): turlar arası hedef koşulu.

    /goal <koşul>      hedefi kur ve ilk turu hedef kipinde başlat
    /goal | durum      hedefin durumu (değerlendirme, otomatik tur, son karar)
    /goal devam        duraklatılmış hedefi sürdür (danışma aralığı katlanır)
    /goal clear        hedefi bırak (temizle, bırak, iptal, off da olur)

İlk tur eski `/goal` makrosuyla aynıdır (hedef kipi istemi + yükseltilmiş adım sınırı,
aynı adlı kullanıcı becerisi önce gelir); fark, her tur sonunda `goal_flow` koşulu
değerlendirip gerekiyorsa turu kendiliğinden sürdürmesidir. İşleyiciler saf ve
senkrondur: görevi yalnız HAZIRLAR (`state.pending_task`), çalıştırmaz.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ...core.session_goal import GoalError, SessionGoal, new_goal, resume
from ...ui import messages
from . import goal_store
from .macros import Mode
from .state import ReplState

Handler = Callable[[ReplState, str], str]

_STATUS_WORDS = frozenset({"durum", "status"})
_CLEAR_WORDS = frozenset({"clear", "temizle", "birak", "bırak", "iptal", "off", "stop"})
_RESUME_WORDS = frozenset({"devam", "resume", "surdur", "sürdür"})


def goal_handler(start_turn: Handler) -> Handler:
    """`/goal` işleyicisi; `start_turn` ilk turu hazırlayan hedef makrosudur."""

    def handler(state: ReplState, argument: str) -> str:
        text = argument.strip()
        word = text.casefold()
        if not text or word in _STATUS_WORDS:
            return status_text(state)
        if word in _CLEAR_WORDS:
            return clear_goal(state)
        if word in _RESUME_WORDS:
            return resume_goal(state)
        try:
            goal = new_goal(
                text, now=time.time(), checkin_minutes=state.config.runtime.goal_checkin_minutes
            )
        except GoalError as error:
            return str(error)
        lines = []
        if state.goal is not None:
            lines.append(messages.GOAL_REPLACED.format(condition=_short(state.goal.condition)))
        set_goal(state, goal)
        lines.append(_set_text(state, goal))
        lines.append(start_turn(state, text))
        return "\n".join(line for line in lines if line)

    return handler


def set_goal(state: ReplState, goal: SessionGoal | None) -> None:
    """Hedefi duruma yaz ve kalıcı kaydı güncelle (tek yazım yolu)."""
    state.goal = goal
    goal_store.save(state.config.memory_dir, state.conversation_id, goal)


def clear_goal(state: ReplState) -> str:
    if state.goal is None:
        return messages.GOAL_NONE
    condition = state.goal.condition
    set_goal(state, None)
    return messages.GOAL_CLEARED.format(condition=_short(condition))


def resume_goal(state: ReplState) -> str:
    goal = state.goal
    if goal is None:
        return messages.GOAL_NONE
    # Etkin hedefte (ör. Durdur sonrası) sayaçlar korunur; yalnız devam turu hazırlanır.
    resumed = goal if goal.is_active else resume(goal, now=time.time())
    set_goal(state, resumed)
    state.pending_task = messages.GOAL_RESUME_TASK.format(
        condition=resumed.condition, reason=resumed.last_reason or "-"
    )
    state.pending_mode = Mode.GOAL
    return messages.GOAL_RESUMED.format(condition=_short(resumed.condition))


def status_text(state: ReplState) -> str:
    goal = state.goal
    if goal is None:
        return messages.GOAL_NONE
    if goal.is_active:
        status = messages.GOAL_STATUS_ACTIVE
    else:
        label = messages.GOAL_PAUSE_LABELS.get(goal.paused.value, goal.paused.value)
        status = messages.GOAL_STATUS_PAUSED.format(reason=label)
    lines = [
        messages.GOAL_STATUS.format(
            condition=_short(goal.condition),
            status=status,
            evaluations=goal.evaluations,
            auto_turns=goal.auto_turns,
            minutes=int((time.time() - goal.started_at) // 60),
        )
    ]
    if goal.last_verdict is not None:
        lines.append(
            messages.GOAL_STATUS_LAST.format(
                verdict=messages.GOAL_VERDICT_LABELS[goal.last_verdict.value],
                reason=goal.last_reason or "-",
            )
        )
    return "\n".join(lines)


def _set_text(state: ReplState, goal: SessionGoal) -> str:
    minutes = state.config.runtime.goal_checkin_minutes
    return messages.GOAL_SET.format(
        condition=_short(goal.condition),
        max_turns=state.config.runtime.goal_max_turns,
        checkin=messages.GOAL_SET_CHECKIN.format(minutes=minutes) if minutes else "",
    )


#: Kullanıcı metinlerinde gösterilen koşul uzunluğu (koşulun tamamı 4.000 karaktere çıkabilir).
_SHORT_CHARS = 160


def _short(condition: str) -> str:
    return condition if len(condition) <= _SHORT_CHARS else condition[:_SHORT_CHARS] + "…"

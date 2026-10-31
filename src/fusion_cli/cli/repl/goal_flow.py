"""Tur sonu hedef değerlendirmesi ve otomatik devam (`/goal`, P-058).

Üç yüzey aynı akışı kullanır: satır-içi REPL (`loop.py`), tam ekran TUI (`tui_loop.py`)
ve masaüstü (`appserver/session.py`). Akış:

    tur biter → hedef etkinse hakem modeli koşulu değerlendirir (`goal_judge`)
      → Tamam / İmkânsız: hedef kapanır, kullanıcıya söylenir
      → Henüz değil: devam görevi üretilir; yüzey onu hedef kipinde yeni tur yapar
      → danışma zamanı, tur tavanı ya da belirsiz karar: hedef duraklar (`/goal devam`)

İptal edilen (Ctrl-C/Esc) tur değerlendirilmez: kullanıcı durdurmak istemiştir.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass

from ...config.models import Config
from ...core.events import Event, EventPublisher, EventSink
from ...core.session_goal import GoalAction, GoalStep, PauseReason, decide
from ...core.types import Message
from ...engines.agent.goal_judge import GoalJudgement, judge_goal
from ...ui import messages
from .goal_command import set_goal
from .state import Engine, ReplState

#: Değerlendirici imzası; testler sahte yargıç verir.
GoalJudge = Callable[
    [str, Sequence[Message], Config, EventPublisher | None], Awaitable[GoalJudgement]
]


@dataclass(frozen=True, slots=True)
class GoalOutcome:
    """Bir değerlendirmenin yüzeye söylediği: gösterilecek metin ve varsa devam görevi."""

    step: GoalStep
    message: str
    next_prompt: str | None


class SinkPublisher:
    """Tur dışında yapılan değerlendirme çağrısının olaylarını sink'lere (maliyet) taşır."""

    def __init__(self, sinks: Iterable[EventSink]) -> None:
        self._sinks = tuple(sinks)

    def publish(self, event: Event) -> None:
        for sink in self._sinks:
            sink.handle(event)


async def evaluate_goal(
    state: ReplState,
    *,
    judge: GoalJudge | None = None,
    publisher: EventPublisher | None = None,
    now: Callable[[], float] = time.time,
) -> GoalOutcome | None:
    """Etkin hedefi son tura göre değerlendir; hedef yoksa ya da duraklatılmışsa None.

    `judge` verilmezse hakem modeli (`goal_judge.judge_goal`) çağrı anında çözülür.
    Fusion motorunda değerlendirme yapılmaz: o tur konuşma geçmişine yazılmaz, hakem
    sonucu göremez (hedef `/agent` ile dönülene kadar bekler).
    """
    goal = state.goal
    if goal is None or not goal.is_active or state.engine is Engine.FUSION:
        return None
    judgement = await (judge or judge_goal)(goal.condition, state.history, state.config, publisher)
    step = decide(
        goal,
        judgement.verdict,
        judgement.reason,
        now=now(),
        max_auto_turns=state.config.runtime.goal_max_turns,
    )
    set_goal(state, step.goal)
    return GoalOutcome(step, outcome_text(step, state, goal.condition), _next_prompt(step))


async def drive_goal(
    state: ReplState,
    run_turn: Callable[[str], Awaitable[bool]],
    say: Callable[[str], None],
    *,
    should_yield: Callable[[], bool] = lambda: False,
    judge: GoalJudge | None = None,
    publisher: EventPublisher | None = None,
) -> None:
    """Hedef kapanana ya da duraklayana kadar değerlendir → devam turu döngüsü.

    `run_turn` turu çalıştırır ve tamamlandıysa True döner (iptal/hata False).
    `should_yield` True ise (kullanıcının sırada mesajı var) devam turu başlatılmaz.
    """
    while True:
        outcome = await evaluate_goal(state, judge=judge, publisher=publisher)
        if outcome is None:
            return
        say(outcome.message)
        if outcome.next_prompt is None:
            return
        if should_yield():
            say(messages.GOAL_WAITING_USER)
            return
        if not await run_turn(outcome.next_prompt):
            return


def outcome_text(step: GoalStep, state: ReplState, condition: str) -> str:
    """Kararın kullanıcı metni."""
    reason = step.reason or "-"
    if step.action is GoalAction.MET:
        return messages.GOAL_MET.format(
            condition=condition[:160], reason=f" — {step.reason}" if step.reason else ""
        )
    if step.action is GoalAction.IMPOSSIBLE:
        return messages.GOAL_IMPOSSIBLE.format(reason=f": {step.reason}" if step.reason else "")
    goal = step.goal
    max_turns = state.config.runtime.goal_max_turns
    if step.action is GoalAction.CONTINUE and goal is not None:
        return messages.GOAL_CONTINUE.format(reason=reason, n=goal.auto_turns, max_turns=max_turns)
    if goal is not None and goal.paused is PauseReason.CHECKIN:
        return messages.GOAL_PAUSED_CHECKIN.format(
            minutes=int((time.time() - goal.started_at) // 60),
            evaluations=goal.evaluations,
            reason=reason,
        )
    if goal is not None and goal.paused is PauseReason.TURN_LIMIT:
        return messages.GOAL_PAUSED_LIMIT.format(max_turns=max_turns, reason=reason)
    return messages.GOAL_PAUSED_UNKNOWN.format(reason=reason)


def _next_prompt(step: GoalStep) -> str | None:
    if step.action is not GoalAction.CONTINUE or step.goal is None:
        return None
    return messages.GOAL_CONTINUE_TASK.format(
        reason=step.reason or "-", condition=step.goal.condition
    )


def wire_payload(outcome: GoalOutcome | None, state: ReplState) -> dict[str, object]:
    """Masaüstü tur sonucuna eklenecek alanlar: `hedef` (durum) ve varsa `hedef_devam`."""
    if outcome is None:
        return {}
    payload: dict[str, object] = {
        "hedef": {
            "karar": outcome.step.verdict.value,
            "eylem": outcome.step.action.value,
            "metin": outcome.message,
            "durum": state.goal.to_dict() if state.goal is not None else None,
        }
    }
    if outcome.next_prompt is not None:
        payload["hedef_devam"] = outcome.next_prompt
    return payload

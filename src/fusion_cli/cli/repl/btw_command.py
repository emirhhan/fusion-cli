"""`/btw [soru]` — konuşma hakkında yan soru; geçmişe girmez (#221, Claude Code).

Claude Code: yan soru mevcut konuşmayı görür ama soru ve cevap konuşma geçmişine HİÇ
girmez; araç kullanılmaz; son yan sorular ayrıca tutulur, argümansız çağrı en sonuncusunu
gösterir, hiç yoksa kullanım satırı basar. Fusion: agent modeline araçsız tek çağrı; sonuç
tam ekranda Claude'daki gibi kapatılabilir bir katmanda gösterilir (←/→ önceki yan sorular,
Esc/Enter kapatır; konuşma alanına basılmaz); satır içi REPL ve masaüstünde ayrı blok olarak
basılır. Transcript'e ve motor geçmişine yazılmaz.
"""

from __future__ import annotations

import textwrap
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from rich.console import Console
from rich.markup import escape

from ...core.types import CompletionRequest, Message, ModelResult
from ...ui import messages, theme
from ...ui.picker import Choice
from .state import ReplState

#: Tutulan en çok yan soru (Claude Code: son 20).
SIDE_QUESTION_LIMIT = 20
#: Yan soruya bağlam olarak verilen en çok son mesaj.
CONTEXT_MESSAGES = 40


class _Completer(Protocol):
    async def complete(self, request: CompletionRequest) -> ModelResult: ...


def _provider(state: ReplState) -> _Completer:
    """Agent modelinin sağlayıcısı; testte sahte verilir."""
    from ...providers.factory import build_provider
    from ...providers.web_registry import web_registry_for

    return build_provider(
        state.config.agent,
        publisher=None,
        retry_delays_s=state.config.runtime.retry_delays_s,
        web_sessions=web_registry_for(state.config),
    )


def build_request(state: ReplState, question: str) -> CompletionRequest:
    """Konuşmanın metin kısmı + yan soru; araç şeması yok."""
    context = [
        Message(m.role, m.content)
        for m in state.history
        if m.role in ("user", "assistant") and not m.harness_note and m.content.strip()
    ][-CONTEXT_MESSAGES:]
    runtime = state.config.runtime
    return CompletionRequest(
        messages=(Message("system", messages.BTW_SYSTEM), *context, Message("user", question)),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
    )


async def ask(state: ReplState, question: str) -> str:
    """Yan soruyu yanıtla; soru/cevap yalnız `state.side_questions`'a yazılır."""
    result = await _provider(state).complete(build_request(state, question))
    answer = (
        result.text.strip()
        if result.ok
        else messages.BTW_FAILED.format(error=result.error or messages.BTW_EMPTY)
    )
    state.side_questions = [*state.side_questions, (question, answer)][-SIDE_QUESTION_LIMIT:]
    return answer


def _print(console: Console, question: str, answer: str) -> None:
    console.print(f"[{theme.DIM}]{escape(messages.BTW_HEADER.format(question=question))}[/]")
    console.print(escape(answer))
    console.print(f"[{theme.DIM}]{escape(messages.BTW_FOOTER)}[/]")


async def render(state: ReplState, argument: str, console: Console) -> None:
    """`help_view.render` girişi: soru varsa yanıtla, yoksa en son yan soruyu göster."""
    question = argument.strip()
    if not question:
        if not state.side_questions:
            console.print(f"[{theme.DIM}]{escape(messages.BTW_USAGE)}[/]")
            return
        _print(console, *state.side_questions[-1])
        return
    _print(console, question, await ask(state, question))


def btw_command(state: ReplState, argument: str) -> str:
    """Eşzamanlı yol (yalnız yedek): yüzeyler `render` kullanır."""
    del argument
    if not state.side_questions:
        return messages.BTW_USAGE
    question, answer = state.side_questions[-1]
    return f"{messages.BTW_HEADER.format(question=question)}\n{answer}"


#: Katmanın satır genişliği; uzun cevap satırları sarılır.
OVERLAY_WIDTH = 96
OVERLAY_KEYS = ("left", "right")
ChoiceAsker = Callable[[str, Sequence[Choice], tuple[str, ...]], Awaitable[str | None]]


def overlay_rows(answer: str) -> tuple[Choice, ...]:
    lines: list[str] = []
    for raw in answer.splitlines() or [""]:
        lines.extend(textwrap.wrap(raw, OVERLAY_WIDTH) or [" "])
    return tuple(Choice(f"satir:{index}", line) for index, line in enumerate(lines))


async def show_overlay(state: ReplState, ask_choice: ChoiceAsker, index: int = -1) -> None:
    """Yan soruyu kapatılabilir katmanda göster; ←/→ önceki/sonraki yan soruya geçer."""
    total = len(state.side_questions)
    position = index % total if total else 0
    while total:
        question, answer = state.side_questions[position]
        title = messages.BTW_OVERLAY_TITLE.format(
            question=question, position=position + 1, total=total
        )
        picked = await ask_choice(title, overlay_rows(answer), OVERLAY_KEYS)
        if picked is None or not picked.startswith(OVERLAY_KEYS):
            return
        step = -1 if picked.startswith("left") else 1
        position = max(0, min(total - 1, position + step))


async def inline_overlay(state: ReplState, argument: str, console: Console) -> None:
    """Satır içi REPL: aynı katman `ui.picker.pick` ile (terminal gerektirir)."""
    from ...ui.picker import pick

    question = argument.strip()
    if not question and not state.side_questions:
        console.print(f"[{theme.DIM}]{escape(messages.BTW_USAGE)}[/]")
        return
    if question:
        await ask(state, question)

    async def _ask(title: str, rows: Sequence[Choice], keys: tuple[str, ...]) -> str | None:
        return pick(rows, title=title, alt_keys=keys)

    await show_overlay(state, _ask)

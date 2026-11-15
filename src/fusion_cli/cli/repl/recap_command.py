"""`/recap` — oturumun tek satırlık özeti, yalnız istenince (#230, Claude Code).

Claude Code: `/recap` geçerli oturumun tek satırlık özetini isteğe bağlı üretir; çıktı 400
karakterle sınırlıdır ve konuşma geçmişinin yerine geçmez (`/compact`'tan farkı budur).
Fusion: `/btw` ile aynı yol — agent modeline araçsız tek çağrı; özet basılır, geçmişe ve
transcript'e yazılmaz. Üç yüzey `help_view.render` üzerinden çalışır.
"""

from __future__ import annotations

from dataclasses import replace

from rich.console import Console
from rich.markup import escape

from ...ui import messages, theme
from . import btw_command
from .state import ReplState

#: Claude Code'un özet sınırı (karakter).
RECAP_MAX_CHARS = 400


def one_line(text: str) -> str:
    """Tek satıra indir ve 400 karakterde kes."""
    flat = " ".join(text.split())
    if len(flat) <= RECAP_MAX_CHARS:
        return flat
    return flat[: RECAP_MAX_CHARS - 1].rstrip() + "…"


async def recap(state: ReplState) -> str:
    """Özeti üret; konuşma yoksa model çağrılmaz."""
    if not any(m.role in ("user", "assistant") and m.content.strip() for m in state.history):
        return messages.RECAP_EMPTY
    request = btw_command.build_request(state, messages.RECAP_REQUEST)
    system = request.messages[0]
    request = replace(
        request, messages=(replace(system, content=messages.RECAP_SYSTEM), *request.messages[1:])
    )
    result = await btw_command._provider(state).complete(request)
    if not result.ok or not result.text.strip():
        return messages.RECAP_FAILED.format(error=result.error or messages.BTW_EMPTY)
    return one_line(result.text)


async def render(state: ReplState, console: Console) -> None:
    """`help_view.render` girişi."""
    text = await recap(state)
    if text == messages.RECAP_EMPTY:
        console.print(f"[{theme.DIM}]{escape(text)}[/]")
        return
    console.print(f"{messages.RECAP_MARK} {escape(text)}", highlight=False)


def recap_command(state: ReplState, argument: str) -> str:
    """Eşzamanlı yol (yalnız yedek): yüzeyler `render` kullanır."""
    del state, argument
    return messages.RECAP_USAGE

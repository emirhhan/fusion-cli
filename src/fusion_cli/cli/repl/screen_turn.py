"""Tur koşucusu — girişi motora bağlar, çıktıyı tam-ekran konuşmaya akıtır.

fusion + agent turları akar. Onay/soru, tam-ekranda `ScreenPrompter` üzerinden
modal diyalogla karşılanır (evet/hayır ve serbest metin).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ...core.events import Event
from ...engines.agent.approval import ApprovalRequest
from ...ui.renderer import ConsoleRenderer
from ..session import run_agent_task, run_task
from .state import Engine
from .work_line import WorkLineSink

if TYPE_CHECKING:  # pragma: no cover
    from .screen import FusionScreen
    from .state import ReplState


class ScreenPrompter:
    """Motor onay/soru çağrılarını tam-ekran modalına köprüler."""

    def __init__(self, screen: FusionScreen) -> None:
        self._screen = screen

    async def confirm(self, request: ApprovalRequest) -> bool:
        return await self._screen.ask_confirm(_preview(request), request.danger)

    async def ask(self, question: str) -> str:
        return await self._screen.ask_text(question)


def _preview(request: ApprovalRequest) -> str:
    """Onaya sunulan araç çağrısının düz metin özeti: araç adı + argümanlar."""
    pairs = ", ".join(f"{key}={value!r}" for key, value in request.args.items())
    return f"{request.tool.name}({pairs})"


class PumpSink:
    """Her olaydan sonra bir geri çağrı tetikler (drain + invalidate + follow)."""

    def __init__(self, on_event: Callable[[], None]) -> None:
        self._on_event = on_event

    def handle(self, event: Event) -> None:
        self._on_event()


async def run_turn(line: str, state: ReplState, screen: FusionScreen) -> None:
    """Bir mesajı aktif motora gönder; çıktıyı tam-ekran konuşmaya akıt.

    Renderer köprülü console'a yazar (live_progress kapalı — Live yerine layout
    çalışma satırı beslenir); work satırı model olaylarından metin üretir; pump
    her olayda köprüyü boşaltıp ekranı tazeler. Maliyet toplayıcı OTURUM boyunca
    yaşar: her tur aynı toplayıcıyı besler.
    """
    renderer = ConsoleRenderer(
        screen.bridge.console, live_progress=False, show_call_details=True
    )
    work = WorkLineSink(screen.set_work, screen.clear_work)
    pump = PumpSink(screen.after_event)
    sinks = (renderer, work, pump, state.cost)

    if state.engine is Engine.FUSION:
        await run_task(
            line,
            state.config,
            sinks=sinks,
            task_type=state.task_type,
            synthesis=state.synthesis,
            memory=state.memory,
        )
    else:
        await run_agent_task(
            line,
            state.config,
            sinks=sinks,
            prompter_factory=lambda _drain: ScreenPrompter(screen),
            mode=state.approval,
            root=state.root,
            interactive=True,
            memory=state.memory,
        )

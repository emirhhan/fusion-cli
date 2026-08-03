"""Tam-ekran tur koşucusu ve komut köprüsü.

Tam-ekran görünüm YALNIZCA bir görünümdür. Normal terminalle aynı komut kayıt
defterini ve `ReplState`'i paylaşır; iptali çağıranın sahip olduğu tek bir görev
denetler. Bu, paralel turları engeller ve Ctrl-C'yi kararlı kılar.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...core.events import Event
from ...engines.agent.approval import ApprovalRequest
from ...ui import messages, theme
from ...ui.renderer import ConsoleRenderer
from ..session import run_agent_task, run_task
from . import help_view
from .commands import RENDERED_COMMANDS, CommandRegistry, parse
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
    pairs = ", ".join(f"{key}={value!r}" for key, value in request.args.items())
    return f"{request.tool.name}({pairs})"


class PumpSink:
    """Her olaydan sonra ANSI köprüsünü boşalt ve uygulamayı yeniden çiz."""

    def __init__(self, on_event: Callable[[], None]) -> None:
        self._on_event = on_event

    def handle(self, event: Event) -> None:
        self._on_event()


def screen_status(state: ReplState) -> str:
    """Tam-ekran görünümün kullandığı kısa ve dürüst durum satırı (etkin modelle)."""
    return (
        f"{state.approval.value} · {state.engine.value} · {state.task_type} · "
        f"{state.config.agent.model} · config {state.config_revision.value}"
    )


async def run_screen_line(
    line: str,
    state: ReplState,
    screen: FusionScreen,
    registry: CommandRegistry,
) -> None:
    """Gönderilen bir satırı ortak komut kayıt defterinden ya da etkin motordan geçir."""
    if state.refresh_config():
        screen.append_text(
            f"\n[ayar] Kontrol paneli değişikliği yüklendi: {state.config.agent.name}\n"
        )
    screen.set_status(screen_status(state))
    ConsoleRenderer(screen.bridge.console).print_user_message(line)
    screen.after_event()

    if line.startswith("/"):
        name, argument = parse(line)
        command = registry.get(name)
        if command is None:
            screen.append_text(f"\nBilinmeyen komut: {name}\n")
            return
        if command.name in RENDERED_COMMANDS:
            await help_view.render(command.name, state, registry, screen.bridge.console)
            screen.after_event()
            return
        # Zaten çalışan bir prompt_toolkit uygulamasının içinde etkileşimli seçiciler
        # alternatif ekranı bozar. Bunların argümanlı biçimi yine de kullanılabilir.
        picker_komutlari = {"model", "provider", "development", "level", "profiles"}
        if command.name in picker_komutlari and not argument.strip():
            screen.append_text(
                f"\n/{command.name} tam-ekranda argüman ister. "
                "Örnek: /level high. Ayrıntı için /help.\n"
            )
            return
        result = command.handler(state, argument)
        if result:
            screen.bridge.console.print(f"[{theme.DIM}]{result}[/{theme.DIM}]")
            screen.after_event()
        screen.set_status(screen_status(state))
        if not state.running:
            screen.request_exit()
            return
        pending, _mode = state.take_pending()
        if pending:
            await run_turn(pending, state, screen)
        return

    await run_turn(line, state, screen)


async def run_turn(line: str, state: ReplState, screen: FusionScreen) -> None:
    """Bir mesajı etkin motora gönder ve çıktısını tam-ekran görünüme akıt."""
    renderer = ConsoleRenderer(screen.bridge.console, live_progress=False, show_call_details=True)
    work = WorkLineSink(screen.set_work, screen.clear_work)
    pump = PumpSink(screen.after_event)
    sinks = (renderer, work, pump, state.cost)

    try:
        if state.engine is Engine.FUSION:
            result = await run_task(
                line,
                state.config,
                sinks=sinks,
                task_type=state.task_type,
                synthesis=state.synthesis,
                memory=state.memory,
                health=state.health,
            )
            state.last_fusion = result
        else:
            outcome = await run_agent_task(
                line,
                state.config,
                sinks=sinks,
                prompter_factory=lambda _drain: ScreenPrompter(screen),
                mode=state.approval,
                task_type=state.task_type,
                root=state.root,
                interactive=True,
                memory=state.memory,
            )
            if hasattr(outcome, "messages"):
                state.history = outcome.messages
    except asyncio.CancelledError:
        screen.append_text(f"\n{messages.REPL_TURN_CANCELLED}\n")
        raise
    finally:
        screen.clear_work()
        close_modal = getattr(screen, "close_modal", None)
        if close_modal is not None:
            close_modal()
        screen.after_event()

"""Ink-benzeri tek yol REPL döngüsü (tam-ekran).

`FusionTui`'yi kurar; gönderilen satırları ortak komut kayıt defterinden ya da etkin
motordan geçirir. Motor çıktısı `FusionTui.console`'a RENKLİ yazılır ve her olaydan sonra
kaydırılabilir konuşma alanına aktarılır. Tur bir asyncio görevinde koşar: esc turu keser,
Ctrl-C fusion'dan çıkar. Onay/soru, `FusionTui`'nin modal desteğiyle köprülenir.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from rich.console import Console

from ...engines.agent.approval import ApprovalRequest
from ...ui import banner, messages, theme
from ...ui.renderer import ConsoleRenderer
from ..session import run_agent_task, run_task
from . import help_view
from .commands import RENDERED_COMMANDS, build_registry, parse
from .state import Engine, ReplState
from .tui import FusionTui
from .work_line import WorkLineSink

_logger = logging.getLogger(__name__)

#: Argümansız çağrıldığında etkileşimli seçici açan komutlar (A5'te satır-içi çözülecek).
_PICKER_COMMANDS = frozenset({"model", "provider", "development", "level", "profiles"})


def _preview(request: ApprovalRequest) -> str:
    """Onay önizlemesi: araç(argümanlar) + varsa tehlike gerekçesi."""
    pairs = ", ".join(f"{key}={value!r}" for key, value in request.args.items())
    body = f"{request.tool.name}({pairs})"
    head = f"[{theme.DIM}]{messages.TUI_CONFIRM_PREVIEW}[/{theme.DIM}] {body}"
    if request.danger:
        return f"{head}\n[{theme.ERROR}]{request.danger}[/{theme.ERROR}]"
    return head


class _PumpSink:
    """Her olaydan sonra konuşma alanını renderer'ın yeni çıktısıyla tazeler."""

    def __init__(self, sync: object) -> None:
        self._sync = sync

    def handle(self, _event: object) -> None:
        if callable(self._sync):
            self._sync()


class TuiPrompter:
    """Motor onay/soru çağrılarını `FusionTui` modaline köprüler."""

    def __init__(self, tui: FusionTui, drain: object) -> None:
        self._tui = tui
        self._drain = drain

    async def confirm(self, request: ApprovalRequest) -> bool:
        await _maybe_drain(self._drain)
        self._tui.console.print(_preview(request))
        self._tui.sync_conversation()
        self._tui.set_work(messages.TUI_CONFIRM_HINT)
        try:
            return await self._tui.await_confirm()
        finally:
            self._tui.clear_work()

    async def ask(self, question: str) -> str:
        await _maybe_drain(self._drain)
        self._tui.console.print(f"[{theme.ACCENT}]{question}[/{theme.ACCENT}]")
        self._tui.sync_conversation()
        return await self._tui.await_text()


async def _maybe_drain(drain: object) -> None:
    if callable(drain):
        result = drain()
        if asyncio.iscoroutine(result):
            await result


class _TuiSession:
    """Tek yol REPL'in çalışma durumu ve olay yönlendirmesi."""

    def __init__(self, state: ReplState) -> None:
        self._state = state
        self._registry = build_registry()
        self._task: asyncio.Task[None] | None = None
        self._tui = FusionTui(
            on_submit=self._submit,
            on_interrupt=self._interrupt,
            on_exit=self._exit,
            on_cycle_mode=self._cycle,
        )
        self._out = self._tui.console
        self._prompter_factory = lambda drain: TuiPrompter(self._tui, drain)
        self._sync_status()

    @property
    def tui(self) -> FusionTui:
        return self._tui

    def _submit(self, text: str) -> None:
        if self._busy:
            return
        line = text.strip()
        if line:
            self._task = asyncio.ensure_future(self._handle(line))

    def _interrupt(self) -> None:
        if self._busy and self._task is not None:
            self._task.cancel()

    def _exit(self) -> None:
        self._state.running = False
        self._tui.request_exit()

    def _cycle(self) -> None:
        self._state.cycle_approval()
        self._sync_status()

    @property
    def _busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def _sync_status(self) -> None:
        self._tui.set_status(self._state.approval.value, self._state.engine.value)

    def _echo(self, renderable: object) -> None:
        """Konuşmaya bir şey yaz ve ekranı tazele."""
        self._out.print(renderable)
        self._tui.sync_conversation()

    async def _handle(self, line: str) -> None:
        try:
            ConsoleRenderer(self._out).print_user_message(line)
            self._tui.sync_conversation()
            if line.startswith("/"):
                await self._command(line)
            else:
                await self._turn(line)
        except asyncio.CancelledError:
            self._echo(f"[{theme.WARN}]{messages.REPL_TURN_CANCELLED}[/{theme.WARN}]")
        except Exception:
            _logger.exception("TUI turu beklenmeyen hatayla bitti")
            self._echo(f"[{theme.ERROR}]{theme.ICON_ERROR} {messages.ERROR_PREFIX}[/{theme.ERROR}]")
        finally:
            self._tui.clear_work()
            self._sync_status()
            if not self._state.running:
                self._tui.request_exit()

    async def _command(self, line: str) -> None:
        name, argument = parse(line)
        command = self._registry.get(name)
        if command is None:
            self._echo(
                f"[{theme.WARN}]{messages.REPL_UNKNOWN_COMMAND.format(name=name)}[/{theme.WARN}]"
            )
            return
        if command.name in RENDERED_COMMANDS:
            await help_view.render(command.name, self._state, self._registry, self._out)
            self._tui.sync_conversation()
            return
        if command.name in _PICKER_COMMANDS and not argument.strip():
            self._echo(
                f"[{theme.DIM}]{messages.TUI_PICKER_NEEDS_ARG.format(name=command.name)}[/{theme.DIM}]"
            )
            return
        result = command.handler(self._state, argument)
        if result:
            self._echo(f"[{theme.DIM}]{result}[/{theme.DIM}]")
        self._sync_status()
        if not self._state.running:
            return
        pending, _mode = self._state.take_pending()
        if pending:
            await self._turn(pending)

    async def _turn(self, line: str) -> None:
        work = WorkLineSink(
            self._tui.set_work, self._tui.clear_work, interrupt_hint=messages.WORK_INTERRUPT_ESC
        )
        renderer = ConsoleRenderer(
            self._out,
            live_progress=False,
            show_thinking=self._state.show_thinking,
            show_call_details=self._state.engine is Engine.FUSION,
            show_all_answers=self._state.show_all_answers,
        )
        pump = _PumpSink(self._tui.sync_conversation)
        sinks = (renderer, work, pump, self._state.cost)
        try:
            if self._state.engine is Engine.FUSION:
                self._state.last_fusion = await run_task(
                    line,
                    self._state.config,
                    sinks=sinks,
                    task_type=self._state.task_type,
                    synthesis=self._state.synthesis,
                    memory=self._state.memory,
                    health=self._state.health,
                )
            else:
                outcome = await run_agent_task(
                    line,
                    self._state.config,
                    sinks=sinks,
                    prompter_factory=self._prompter_factory,
                    mode=self._state.approval,
                    task_type=self._state.task_type,
                    root=self._state.root,
                    interactive=True,
                    memory=self._state.memory,
                    history=self._state.history,
                )
                self._state.history = outcome.messages
        finally:
            renderer.abort()
            self._tui.sync_conversation()


async def run_tui_repl(state: ReplState, console: Console) -> int:
    """Ink-benzeri tek yol REPL'i çalıştır. Çıkış kodunu döndürür."""
    from .loop import session_info

    session = _TuiSession(state)
    # Açılış kutusu konuşma alanına yazılır (tam-ekranda üstte durur).
    banner.print_welcome(session.tui.console, session_info(state), clear=False, pad=False)
    session.tui.sync_conversation()

    await session.tui.application.run_async()

    # Çıkışta konuşmayı gerçek terminale dök: tam-ekran kapanınca scrollback kaybolmasın.
    sys.stdout.write(session.tui.transcript)
    sys.stdout.flush()
    return 0

"""REPL ana döngüsü.

Akış basittir ve bilinçli olarak öyledir:

    prompt aç → satır al → prompt KAPAT → turu çalıştır → tekrar

Giriş satırı ve çalışan tur asla aynı anda ekranda olmaz. Eski projede kalıcı bir
giriş satırıyla akan çıktı aynı anda imleci yönetiyordu ve satırlar birbirini
bozuyordu; buradaki sıralı model o hata sınıfını tamamen ortadan kaldırır.

Çalışan turu Ctrl-C keser ve REPL'den çıkılmaz. Öğrenme işleri (ders çıkarımı)
arka planda sürer, kullanıcı yazarken tamamlanır ve çıkışta beklenir.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Iterator
from pathlib import Path

from rich.console import Console

from ...config.models import Config
from ...core.concurrency import BackgroundTasks
from ...core.events import ErrorOccurred, TurnFinished
from ...core.tools import ToolContext
from ...core.types import FusionResult
from ...engines.agent.compaction import compress
from ...memory.factory import Memory
from ...observability.bus import EventBus
from ...ui import banner, messages, theme
from ...ui.renderer import ConsoleRenderer
from ..prompter import ConsolePrompter
from . import help_view
from .commands import RENDERED_COMMANDS, CommandRegistry, build_registry, parse
from .input import ReplInput
from .state import Engine, ReplState

#: Komut geçmişinin saklandığı dosya adı.
HISTORY_FILE = "repl_history"


async def run_repl(config: Config, *, memory: Memory, root: Path, console: Console) -> int:
    """İnteraktif oturumu çalıştır. Çıkış kodunu döndürür."""
    state = ReplState(config=config, memory=memory, root=root)
    registry = build_registry()
    reader = ReplInput(
        config.memory_dir / HISTORY_FILE, registry.completion_words(), mode=state.approval
    )
    background = BackgroundTasks()

    banner.print_banner(console)
    _print_status(console, state)
    if not memory.enabled:
        console.print(
            f"[{theme.WARN}]"
            f"{messages.MEMORY_UNAVAILABLE.format(reason=memory.unavailable_reason)}"
            f"[/{theme.WARN}]"
        )
    console.print()

    try:
        while state.running:
            line = await _read_line(reader, state)
            if line is None:
                break
            if not line.strip():
                continue
            await _handle(line.strip(), state, registry, reader, console, background)
    finally:
        await _shutdown(background, console)
    return 0


async def _read_line(reader: ReplInput, state: ReplState) -> str | None:
    """Kullanıcıdan satır al. Ctrl-D/EOF'ta None döner (çıkış)."""
    try:
        line = await reader.prompt()
    except (EOFError, KeyboardInterrupt):
        return None
    # shift-tab girişte modu değiştirmiş olabilir; durumu senkronla.
    state.approval = reader.mode
    return line


async def _handle(
    line: str,
    state: ReplState,
    registry: CommandRegistry,
    reader: ReplInput,
    console: Console,
    background: BackgroundTasks,
) -> None:
    if line.startswith("/"):
        await _run_command(line, state, registry, reader, console)
        return
    await _run_turn(line, state, console, background)


async def _run_command(
    line: str, state: ReplState, registry: CommandRegistry, reader: ReplInput, console: Console
) -> None:
    name, argument = parse(line)
    command = registry.get(name)
    if command is None:
        console.print(
            f"[{theme.WARN}]{messages.REPL_UNKNOWN_COMMAND.format(name=name)}[/{theme.WARN}]"
        )
        return

    if command.name in RENDERED_COMMANDS:
        await help_view.render(command.name, state, registry, console)
        return

    result = command.handler(state, argument)
    reader.mode = state.approval
    if result:
        console.print(f"[{theme.DIM}]{result}[/{theme.DIM}]")
    if command.name in {"agent", "fusion", "auto", "plan", "security", "type"}:
        _print_status(console, state)


# --------------------------------------------------------------------------- #
# Tur çalıştırma
# --------------------------------------------------------------------------- #


async def _run_turn(
    line: str, state: ReplState, console: Console, background: BackgroundTasks
) -> None:
    """Bir mesajı aktif motora gönder. Ctrl-C turu keser, REPL'den çıkmaz."""
    task = asyncio.ensure_future(_dispatch(line, state, console, background))
    with _cancel_on_interrupt(task):
        try:
            await task
        except asyncio.CancelledError:
            console.print(f"[{theme.WARN}]{messages.REPL_TURN_CANCELLED}[/{theme.WARN}]")
    console.print()


async def _dispatch(
    line: str, state: ReplState, console: Console, background: BackgroundTasks
) -> None:
    if state.engine is Engine.FUSION:
        await _fusion_turn(line, state, console)
    else:
        await _agent_turn(line, state, console, background)


async def _fusion_turn(line: str, state: ReplState, console: Console) -> None:
    from ..session import run_task

    renderer = ConsoleRenderer(console, show_all_answers=state.show_all_answers)
    result: FusionResult = await run_task(
        line,
        state.config,
        sinks=(renderer,),
        task_type=state.task_type,
        synthesis=state.synthesis,
        memory=state.memory,
    )
    state.last_fusion = result


async def _agent_turn(
    line: str, state: ReplState, console: Console, background: BackgroundTasks
) -> None:
    from ...engines.agent import run_agent
    from ...engines.agent.approval import build_policy
    from ...engines.agent.loop import AgentDeps

    renderer = ConsoleRenderer(console)
    async with EventBus() as bus:
        bus.subscribe(renderer)
        prompter = ConsolePrompter(console, ToolContext(root=state.root), flush=bus.drain)
        deps = AgentDeps(
            config=state.config,
            publisher=bus,
            policy=build_policy(state.approval, prompter),
            tool_context=ToolContext(root=state.root),
            asker=prompter,
            code_index=state.memory.code_index if state.memory.enabled else None,
            lessons=state.memory.lessons,
            background=background,
        )
        outcome = await run_agent(
            line,
            deps,
            history=state.history,
            plan_mode=state.approval.value == "plan",
        )
        if not outcome.final_text.strip():
            bus.publish(ErrorOccurred(messages.AGENT_EMPTY_ANSWER))
        bus.publish(TurnFinished())
    state.history = outcome.messages


async def compact_history(state: ReplState) -> str:
    """`/compact`: uzun geçmişi özetleyerek kısalt."""
    before = len(state.history)
    state.history = await compress(state.history, config=state.config)
    after = len(state.history)
    if after >= before:
        return messages.REPL_NOTHING_TO_COMPACT
    return messages.REPL_COMPACTED.format(before=before, after=after)


# --------------------------------------------------------------------------- #
# Kapanış ve kesme
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _cancel_on_interrupt(task: asyncio.Future[None]) -> Iterator[None]:
    """Ctrl-C çalışan turu iptal etsin, süreci sonlandırmasın.

    Sinyal işleyicisi kurulamayan platformlarda (Windows) sessizce geçilir; orada
    KeyboardInterrupt normal akışıyla yakalanır.
    """
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, task.cancel)
    except (NotImplementedError, RuntimeError, ValueError):
        yield
        return
    try:
        yield
    finally:
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.remove_signal_handler(signal.SIGINT)


async def _shutdown(background: BackgroundTasks, console: Console) -> None:
    """Arka plandaki öğrenme işlerini tamamla; öğrenilen ders kaybolmasın."""
    if background.pending:
        console.print(f"[{theme.DIM}]{messages.REPL_BACKGROUND_WAIT}[/{theme.DIM}]")
        await background.drain()
    for failure in background.failures:
        console.print(f"[{theme.DIM}]arka plan: {failure}[/{theme.DIM}]")
    console.print(f"[{theme.DIM}]{messages.REPL_GOODBYE}[/{theme.DIM}]")


def _print_status(console: Console, state: ReplState) -> None:
    banner.print_status(
        console,
        engine=state.engine.value,
        approval=state.approval.value,
        task_type=state.task_type,
        model=state.config.agent.name,
    )

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
from ...observability.tracing import LangfuseTracer
from ...ui import banner, messages, theme
from ...ui.renderer import ConsoleRenderer
from ..prompter import ConsolePrompter
from . import help_view, macros
from .commands import RENDERED_COMMANDS, CommandRegistry, build_registry, parse
from .input import ReplInput
from .macros import Mode
from .state import Engine, Reminder, ReplState

#: Komut geçmişinin saklandığı dosya adı.
HISTORY_FILE = "repl_history"

#: Hedef kipinde adım sınırı yükselir: pes etmemek daha çok deneme gerektirir.
GOAL_STEP_LIMIT = 100


async def run_repl(config: Config, *, memory: Memory, root: Path, console: Console) -> int:
    """İnteraktif oturumu çalıştır. Çıkış kodunu döndürür."""
    import os

    if os.environ.get("FUSION_FULLSCREEN") == "1":
        from .screen import run_screen_repl

        state = ReplState(config=config, memory=memory, root=root)
        return await run_screen_repl(state)

    state = ReplState(config=config, memory=memory, root=root)
    registry = build_registry()
    reader = ReplInput(
        config.memory_dir / HISTORY_FILE, registry.completion_words(), mode=state.approval
    )
    background = BackgroundTasks()

    # Modeli arka planda ısıt: soğuk bir uç ilk turda 15-30 sn bekletebiliyor.
    # Kullanıcı banner'ı okuyup ilk komutunu yazarken bu süre geçmiş olur.
    background.spawn(_warm_up(state))

    banner.print_welcome(console, session_info(state))
    _sync_status_bar(reader, state)

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


def _arm_reminders(state: ReplState, console: Console, background: BackgroundTasks) -> None:
    """Kurulmuş hatırlatmaları arka plan işine çevir."""
    for reminder in state.reminders:
        background.spawn(_remind(reminder, console))
    state.reminders.clear()


async def _remind(reminder: Reminder, console: Console) -> None:
    await asyncio.sleep(reminder.due_in_seconds)
    console.print(f"[{theme.WARN}]{reminder.text}[/{theme.WARN}]")


async def _warm_up(state: ReplState) -> None:
    """Agent modeline en küçük çağrıyı yap; sonucu yok sayılır.

    Amaç yalnızca sağlayıcı tarafındaki soğuk başlangıcı tetiklemektir. Hata
    olursa sessizce geçilir: ısıtma bir iyileştirmedir, oturumu etkilememeli.
    """
    from ...core.types import CompletionRequest, Message
    from ...providers.factory import build_provider

    request = CompletionRequest(
        messages=(Message("user", "hi"),),
        temperature=state.config.runtime.judge_temperature,
        max_tokens=1,
        timeout_s=state.config.runtime.request_timeout_s,
        max_retries=0,
    )
    # Sessiz sağlayıcı: ısıtma ne gösterilir ne de muhasebeye girer (1 token).
    await build_provider(
        state.config.agent,
        publisher=None,
        hedge_delay_s=state.config.runtime.hedge_delay_s,
    ).complete(request)


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
    if state.welcome_padded:
        # Açılış dolgusu konuşmanın ortasında dev bir boşluğa dönüşmesin.
        banner.print_welcome(console, session_info(state), pad=False)
        state.welcome_padded = False
    ConsoleRenderer(console).print_user_message(line)
    if line.startswith("/"):
        await _run_command(line, state, registry, reader, console)
        # Makrolar görev HAZIRLAR, çalıştırmaz: komut işleyicileri saf ve senkron
        # kalsın diye çalıştırma buraya bırakılmıştır.
        _arm_reminders(state, console, background)
        task, mode = state.take_pending()
        if task:
            await _run_turn(task, state, console, background, mode=mode)
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
    _sync_status_bar(reader, state)
    if result:
        console.print(f"[{theme.DIM}]{result}[/{theme.DIM}]")
    # `level`/`development` model değiştirir: durum satırındaki model adı bayatlamasın.
    if command.name in {
        "agent",
        "fusion",
        "auto",
        "plan",
        "security",
        "type",
        "level",
        "development",
    }:
        _print_status(console, state)


# --------------------------------------------------------------------------- #
# Tur çalıştırma
# --------------------------------------------------------------------------- #


async def _run_turn(
    line: str,
    state: ReplState,
    console: Console,
    background: BackgroundTasks,
    *,
    mode: Mode = Mode.NONE,
) -> None:
    """Bir mesajı aktif motora gönder. Ctrl-C turu keser, REPL'den çıkmaz."""
    task = asyncio.ensure_future(_dispatch(line, state, console, background, mode))
    with _cancel_on_interrupt(task):
        try:
            await task
        except asyncio.CancelledError:
            console.print(f"[{theme.WARN}]{messages.REPL_TURN_CANCELLED}[/{theme.WARN}]")
    console.print()


async def _dispatch(
    line: str,
    state: ReplState,
    console: Console,
    background: BackgroundTasks,
    mode: Mode = Mode.NONE,
) -> None:
    if state.engine is Engine.FUSION:
        await _fusion_turn(line, state, console)
    else:
        await _agent_turn(line, state, console, background, mode)


async def _fusion_turn(line: str, state: ReplState, console: Console) -> None:
    from ..session import run_task

    renderer = ConsoleRenderer(
        console, show_all_answers=state.show_all_answers, show_call_details=True
    )
    tracer = LangfuseTracer(task=line)
    try:
        result: FusionResult = await run_task(
            line,
            state.config,
            # Maliyet toplayıcı OTURUM boyunca yaşar: her tur aynı toplayıcıyı besler.
            sinks=(renderer, state.cost, tracer),
            task_type=state.task_type,
            synthesis=state.synthesis,
            memory=state.memory,
        )
    finally:
        tracer.flush()
    state.last_fusion = result


async def _agent_turn(
    line: str,
    state: ReplState,
    console: Console,
    background: BackgroundTasks,
    mode: Mode = Mode.NONE,
) -> None:
    from ...engines.agent import run_agent
    from ...engines.agent.approval import build_policy
    from ...engines.agent.loop import AgentDeps
    from ...engines.agent.verification import build_verifier

    renderer = ConsoleRenderer(console)
    tracer = LangfuseTracer(task=line)
    async with EventBus() as bus:
        bus.subscribe(renderer)
        bus.subscribe(state.cost)
        bus.subscribe(tracer)
        tool_context = ToolContext(root=state.root)
        prompter = ConsolePrompter(
            console,
            tool_context,
            flush=bus.drain,
            # Soru/onay sırasında canlı "hazırlanıyor…" satırını duraklat; yoksa
            # spinner cevap istemini ezip kullanıcıyı yazamaz hâle getirir.
            suspend=renderer.suspended,
        )
        deps = AgentDeps(
            config=state.config,
            publisher=bus,
            policy=build_policy(state.approval, prompter),
            tool_context=tool_context,
            asker=prompter,
            code_index=state.memory.code_index if state.memory.enabled else None,
            lessons=state.memory.lessons,
            capabilities=state.capabilities,
            allowed_commands=state.allowed_commands,
            background=background,
            verifier=build_verifier(state.config, root=state.root, tool_context=tool_context),
            # `/type` agent turunda da etkili olmalı: görev tipi model seçimini
            # yönlendirir (`select_agent_spec`). Geçirilmediğinde "general"a düşülüyor
            # ve `task_model_map` REPL'de sessizce uygulanmıyordu.
            task_type=state.task_type,
        )
        outcome = await run_agent(
            line,
            deps,
            history=state.history,
            plan_mode=state.approval.value == "plan",
            extra_system=macros.mode_prompt(mode),
            step_limit=GOAL_STEP_LIMIT if mode is Mode.GOAL else None,
        )
        # Turun değişiklik kaydı `/undo` için saklanır; bir sonraki tur onu ezer.
        state.last_changes = tool_context.changes
        if not outcome.final_text.strip():
            bus.publish(ErrorOccurred(messages.AGENT_EMPTY_ANSWER))
        bus.publish(TurnFinished())
    tracer.flush()
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


def _sync_status_bar(reader: ReplInput, state: ReplState) -> None:
    """Durum çubuğundaki bağlamı güncel tut (motor, görev tipi, model)."""
    reader.context = f"{state.engine.value} · {state.task_type} · {state.config.agent.name}"


def session_info(state: ReplState) -> banner.SessionInfo:
    """Karşılama kutusunda gösterilecek oturum bilgilerini topla."""
    from ... import __version__

    return banner.SessionInfo(
        version=__version__,
        engine=state.engine.value,
        approval=state.approval.value,
        model=state.config.agent.name,
        working_dir=_short_path(state.root),
        lesson_count=state.memory.lessons.count() if state.memory.enabled else None,
    )


#: Bilgi satırında gösterilecek en fazla yol parçası. Uzun yollar satırı sardırıyor.
PATH_SEGMENTS = 2


def _short_path(path: Path) -> str:
    """Yolu kısalt: ev dizini `~`, geri kalanı son birkaç parça."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        parts = path.parts
        if len(parts) <= PATH_SEGMENTS:
            return str(path)
        return "…/" + "/".join(parts[-PATH_SEGMENTS:])


def _print_status(console: Console, state: ReplState) -> None:
    banner.print_status(
        console,
        engine=state.engine.value,
        approval=state.approval.value,
        task_type=state.task_type,
        model=state.config.agent.name,
    )

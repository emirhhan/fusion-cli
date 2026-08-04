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
from collections.abc import Callable, Sequence

from rich.console import Console

from ...config.models import Config
from ...core.concurrency import BackgroundTasks
from ...engines.agent.approval import ApprovalRequest
from ...ui import banner, messages, theme
from ...ui.picker import Choice
from ...ui.renderer import ConsoleRenderer
from ..session import run_agent_task, run_task
from . import help_view, model_flows
from .commands import RENDERED_COMMANDS, build_registry, parse
from .state import Engine, ReplState
from .transcript_store import TranscriptStore
from .tui import FusionTui
from .work_line import WorkLineSink

_logger = logging.getLogger(__name__)

#: Argümansız çağrıldığında uygulama-İÇİ seçim modalıyla çözülen komutlar (nested picker YOK):
#: seçenek üreticisi + başlık. Seçilen değer handler'a ARGÜMAN olarak verilir (handler
#: argümanla seçici açmadan uygular).
_IN_APP_CHOICE: dict[str, tuple[Callable[[Config], Sequence[Choice]], str]] = {
    "mode": (model_flows.mode_choices, messages.MODE_TITLE),
    "level": (model_flows.level_choices, messages.LEVEL_TITLE),
    "effort": (lambda _config: model_flows.effort_choices(), messages.EFFORT_TITLE),
}


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


def _would_open_picker(name: str, argument: str) -> bool:
    """Bu çağrı nested bir prompt_toolkit seçicisi/metin istemi açar mı? (TUI'de guard'lanır.)"""
    arg = argument.strip().lower()
    if name == "provider":
        return True  # argümandan bağımsız her zaman gizli anahtar istemi açar
    if name == "development":
        # Argümansız çağrı uygulama-içi modalda çözülür; argümanlı eski yol
        # nested picker riski taşır ve guard tarafından engellenir.
        return bool(arg)
    if name == "model" and not arg:
        return True  # argümansız katalog seçicisi açar
    if name == "profiles" and arg.startswith("edit"):
        return True  # baş model seçicisi açar
    return name == "providers" and arg.startswith("add")  # gizli anahtar istemi açar


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
        # Tur çalışırken gönderilen satırlar SESSİZCE DÜŞMEZ; kuyruğa alınır ve tur
        # bitince sırayla işlenir (kullanıcının alıştığı davranış — Claude da kuyruklar).
        self._queue: list[str] = []
        # Ders çıkarımı gibi tur-sonrası işler burada fire-and-forget çalışır; cevabı
        # bekletmezler. Çıkışta drain edilir (RULES: her task'ın sahibi vardır).
        self._background = BackgroundTasks()
        self._transcript_store = TranscriptStore(state.config.memory_dir, state.root)
        # Eski ANSI snapshot tekrar yüklenmez; banner çoğalması kesin olarak biter.
        # events.jsonl denetim kaydı sink olarak kullanılmaya devam eder.
        self._tui = FusionTui(
            on_submit=self._submit,
            on_interrupt=self._interrupt,
            on_exit=self._exit,
            on_cycle_mode=self._cycle,
            initial_transcript="",  # TUI isolation: yalnız mevcut oturum
            on_transcript_change=None,
        )
        self._out = self._tui.console
        self._prompter_factory = lambda drain: TuiPrompter(self._tui, drain)
        self._sync_status()

    @property
    def tui(self) -> FusionTui:
        return self._tui

    @property
    def background(self) -> BackgroundTasks:
        return self._background

    def _submit(self, text: str) -> None:
        line = text.strip()
        if not line:
            return
        if self._busy:
            # Tur çalışıyor: düşürme, kuyruğa al ve kullanıcıya kısaca bildir.
            self._queue.append(line)
            self._echo(f"[{theme.DIM}]{messages.TUI_QUEUED.format(line=line)}[/{theme.DIM}]")
            return
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
            self._transcript_store.record_user(line)
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
            elif self._queue:
                # Bu tur bitti; kuyruktaki bir sonraki satırı işle (sıralı, tek sahip).
                self._task = asyncio.ensure_future(self._handle(self._queue.pop(0)))

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
        # Basit seçiciler (mode/level/effort): uygulama-içi modalla çöz, seçileni argüman yap.
        if command.name in _IN_APP_CHOICE and not argument.strip():
            builder, title = _IN_APP_CHOICE[command.name]
            selected = await self._tui.await_choice(title, list(builder(self._state.config)))
            if selected is None:
                self._echo(f"[{theme.DIM}]{messages.PICKER_CANCELLED}[/{theme.DIM}]")
                return
            argument = selected
        elif command.name == "development":
            # İki adımlı (kaynak→model) seçim: nested prompt_toolkit seçicisi TUI'yi
            # bozardı; uygulama-içi modalla sürülür. Argüman verilse bile modal açılır.
            await self._run_development()
            return
        elif _would_open_picker(command.name, argument):
            # Nested picker açacak komutlar TUI'yi bozuyordu; bu görünümde argümanla kullanılır.
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

    async def _run_development(self) -> None:
        """TUI'de `/development`: kaynak→model seçimini uygulama-içi modalla sür.

        Plain REPL'deki iç-içe prompt_toolkit seçicisi tam-ekran TUI'yi bozardı; burada
        aynı `await_choice` modalı iki kez çağrılır. Uygulama/kaydetme mantığı
        `model_flows.apply_development_model` üzerinden ORTAK yürür (kopya yol açılmaz).
        """
        config = self._state.config
        source_key = await self._tui.await_choice(
            messages.DEV_SOURCE_TITLE, list(model_flows.source_choices(config))
        )
        source = model_flows.source_by_key(config, source_key)
        if source is None:
            self._echo(f"[{theme.DIM}]{messages.PICKER_CANCELLED}[/{theme.DIM}]")
            return

        if source.fetcher is None:
            self._tui.console.print(f"[{theme.ACCENT}]{messages.DEV_CUSTOM_PROMPT}[/{theme.ACCENT}]")
            self._tui.sync_conversation()
            model_id: str | None = (await self._tui.await_text()).strip() or None
        else:
            entries = source.fetcher()
            if not entries:
                self._echo(f"[{theme.DIM}]{messages.DEV_EMPTY_CATALOG}[/{theme.DIM}]")
                return
            model_id = await self._tui.await_choice(
                messages.DEV_MODEL_TITLE.format(source=source.label),
                list(model_flows.entries_to_choices(entries, config.profile_eligibility)),
            )

        if model_id is None:
            self._echo(f"[{theme.DIM}]{messages.PICKER_CANCELLED}[/{theme.DIM}]")
            return

        result = model_flows.apply_development_model(config, model_id, paid=source.paid)
        self._state.config = result.config
        self._echo(f"[{theme.DIM}]{result.message}[/{theme.DIM}]")
        self._sync_status()

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
        sinks = (renderer, work, self._transcript_store, pump, self._state.cost)
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
                    background=self._background,
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

    # TUI isolation: ana terminal scrollback + ekranı temizle.
    sys.stdout.write("\x1b[3J\x1b[2J\x1b[H")
    sys.stdout.flush()
    await session.tui.application.run_async()

    # Bekleyen arka plan işlerini (ders çıkarımı) bitir; hataları yut ma, log'la.
    await session.background.drain()
    for failure in session.background.failures:
        _logger.warning("arka plan işi başarısız: %s", failure)

    # Çıkışta konuşmayı gerçek terminale dök: tam-ekran kapanınca scrollback kaybolmasın.
    sys.stdout.write(session.tui.transcript)
    sys.stdout.flush()
    return 0

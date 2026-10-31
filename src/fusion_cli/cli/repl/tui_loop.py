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
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from ...config import keybindings
from ...config.browser_profiles import browser_session_from
from ...config.models import Config
from ...config.permissions import has_untrusted_permissions
from ...core.concurrency import BackgroundTasks
from ...core.tools import ToolContext
from ...engines.agent.approval import ApprovalAnswer, ApprovalRequest
from ...engines.agent.engine_tools import QuestionOption
from ...history import source_by_name
from ...ui import banner, messages, theme
from ...ui.picker import Choice
from ...ui.renderer import ConsoleRenderer
from ...ui.text import summarize_error
from ..rule_notices import print_rule_notices
from ..session import run_agent_task, run_task
from . import (
    help_view,
    history_view,
    macros,
    model_flows,
    output_style_command,
    prefixes,
    profiles_flow,
    provider_flow,
    remote_control,
    rewind,
    session_resume,
    status_line,
    status_view,
    verify_flow,
    view_commands,
    worktrees,
)
from .commands import (
    ASYNC_COMMANDS,
    RENDERED_COMMANDS,
    RESUME_LIST_LIMIT,
    build_registry,
    is_command_line,
    parse,
    resume_choices,
)
from .completion import ReplCompleter
from .loop import apply_auto_profile, apply_mentions, run_shell_prefix_line
from .partial_turn import PartialTurn
from .skill_commands import skill_prefix_to_slash
from .state import Engine, Reminder, ReplState
from .transcript_store import TranscriptStore, list_conversations
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
    """Onay önizlemesi: araç(argümanlar) + varsa tehlike gerekçesi.

    Araç adı, argümanlar (komut metni, dosya içeriği) ve gerekçe Rich işaretinden
    KAÇIRILIR: argümandaki `[/x]` onay akışını çökertir, `[foo]` biçimli parça ise
    sessizce yutulur ve kullanıcı çalışacak komuttan farklı bir metni onaylardı (L2-05).
    """
    pairs = ", ".join(f"{key}={value!r}" for key, value in request.args.items())
    body = escape(f"{request.tool.name}({pairs})")
    head = f"[{theme.DIM}]{messages.TUI_CONFIRM_PREVIEW}[/{theme.DIM}] {body}"
    if request.danger:
        return f"{head}\n[{theme.ERROR}]{escape(request.danger)}[/{theme.ERROR}]"
    if request.note:
        return f"{head}\n[{theme.DIM}]{escape(request.note)}[/{theme.DIM}]"
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

    def __init__(self, tui: FusionTui, drain: object, root: Path | None = None) -> None:
        self._tui = tui
        self._drain = drain
        self._root = root

    def _state_root(self) -> Path | None:
        return self._root

    async def confirm(self, request: ApprovalRequest) -> ApprovalAnswer:
        await _maybe_drain(self._drain)
        self._tui.console.print(_preview(request))
        self._tui.sync_conversation()
        previous_work = self._tui.work_source
        self._tui.set_work_source(lambda: messages.TUI_CONFIRM_HINT)
        try:
            deny = Choice("deny", messages.TUI_APPROVAL_DENY, messages.TUI_APPROVAL_DENY_DESC)
            # Tehlikeli (geri alınamaz) istekte ilk/öntanımlı seçenek RED'dir: art arda
            # basılan Enter işlemi onaylamasın (L1-01).
            choices = [deny] if request.danger else []
            choices.append(
                Choice("once", messages.TUI_APPROVAL_ONCE, messages.TUI_APPROVAL_ONCE_DESC)
            )
            if request.can_remember:
                choices.append(
                    Choice(
                        "session",
                        messages.TUI_APPROVAL_SESSION,
                        request.remembered_scope_description or messages.TUI_APPROVAL_SESSION_DESC,
                    )
                )
            if request.can_persist:
                from ...engines.agent.permission_persist import always_description

                choices.append(
                    Choice(
                        "always",
                        messages.TUI_APPROVAL_ALWAYS,
                        always_description(request, self._state_root()),
                    )
                )
            if not request.danger:
                choices.append(deny)
            answer = await self._tui.await_choice(messages.TUI_APPROVAL_TITLE, choices)
            if answer == "once":
                return ApprovalAnswer.ONCE
            if answer == "session" and request.can_remember:
                return ApprovalAnswer.SESSION
            if answer == "always" and request.can_persist:
                return ApprovalAnswer.ALWAYS
            return ApprovalAnswer.DENY
        finally:
            if previous_work is None:
                self._tui.clear_work()
            else:
                self._tui.set_work_source(previous_work)

    async def ask(
        self,
        question: str,
        options: tuple[QuestionOption, ...] = (),
        recommended: str | None = None,
    ) -> str:
        await _maybe_drain(self._drain)
        self._tui.console.print(f"[{theme.ACCENT}]{escape(question)}[/{theme.ACCENT}]")
        self._tui.sync_conversation()
        if options:
            choices = [
                Choice(
                    option.label,
                    option.label,
                    _option_description(option, recommended),
                )
                for option in options
            ]
            choices.append(Choice("__other__", messages.ASK_OTHER, messages.ASK_OTHER_DESC))
            selected = await self._tui.await_choice(question, choices)
            if selected is None:
                # Esc: kullanıcı KASITLI vazgeçti, ortam etkileşimli (L1-19).
                return messages.ASK_DECLINED
            if selected != "__other__":
                return selected
        answer = await self._tui.await_text()
        # Esc ya da boş Enter boş metin döndürürdü; model boş yanıt alıp aynı soruyu
        # tekrar soruyordu (L2-23).
        return answer if answer.strip() else messages.ASK_DECLINED


def _option_description(option: QuestionOption, recommended: str | None) -> str:
    parts = [option.description] if option.description else []
    if option.label == recommended:
        parts.append(messages.ASK_RECOMMENDED)
    return " · ".join(parts)


def _would_open_picker(name: str, argument: str) -> bool:
    """Bu çağrı nested bir prompt_toolkit seçicisi/metin istemi açar mı? (TUI'de guard'lanır.)

    `/provider`, `/verify` ve `/profiles edit` uygulama-içi modalla çözülür (`_picker_flow`);
    argümansız `/model` yalnız listeler, seçici açmaz (L2-14).
    """
    arg = argument.strip().lower()
    if name == "development":
        # Argümansız çağrı uygulama-içi modalda çözülür; argümanlı eski yol
        # nested picker riski taşır ve guard tarafından engellenir.
        return bool(arg)
    return name == "providers" and arg.startswith("add")  # gizli anahtar istemi açar


def _profile_edit_target(argument: str) -> tuple[str, bool] | None:
    """`/profiles edit <profil> [incompatible]` → (profil, uyumsuzları göster); değilse None."""
    parts = argument.split()
    if len(parts) < 2 or parts[0].lower() != "edit":
        return None
    return parts[1], len(parts) > 2 and parts[2].lower() == "incompatible"


async def _maybe_drain(drain: object) -> None:
    if callable(drain):
        result = drain()
        if asyncio.iscoroutine(result):
            await result


class _TuiSession:
    """Tek yol REPL'in çalışma durumu ve olay yönlendirmesi."""

    def __init__(self, state: ReplState) -> None:
        self._state = state
        self._registry = build_registry(state.home, skills=lambda: state.capabilities)
        self._task: asyncio.Task[None] | None = None
        # Tur çalışırken gönderilen satırlar SESSİZCE DÜŞMEZ; kuyruğa alınır ve tur
        # bitince sırayla işlenir (kullanıcının alıştığı davranış — Claude da kuyruklar).
        self._queue: list[str] = []
        # Ders çıkarımı gibi tur-sonrası işler burada fire-and-forget çalışır; cevabı
        # bekletmezler. Çıkışta drain edilir (RULES: her task'ın sahibi vardır).
        self._background = BackgroundTasks()
        self._transcript_store = TranscriptStore(
            state.config.memory_dir, state.root, conversation_id=state.conversation_id
        )
        # Eski ANSI snapshot tekrar yüklenmez; banner çoğalması kesin olarak biter.
        # events.jsonl denetim kaydı sink olarak kullanılmaya devam eder.
        self._tui = FusionTui(
            on_submit=self._submit,
            on_interrupt=self._interrupt,
            on_exit=self._exit,
            on_cycle_mode=self._cycle,
            initial_transcript="",  # TUI isolation: yalnız mevcut oturum
            on_transcript_change=None,
            completer=ReplCompleter(
                self._registry.completion_words, (state.root, *state.extra_roots)
            ),
            # Boş girdide Esc Esc: Claude Code'daki gibi `/rewind` seçicisini açar.
            on_rewind=lambda: self._submit("/rewind"),
        )
        self._out = self._tui.console
        self._prompter_factory = lambda drain: TuiPrompter(self._tui, drain, self._state.root)
        self._custom_status = ""
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
            self._echo(
                f"[{theme.DIM}]{escape(messages.TUI_QUEUED.format(line=line))}[/{theme.DIM}]"
            )
            return
        self._task = asyncio.ensure_future(self._handle(line))

    def _interrupt(self) -> None:
        if self._busy and self._task is not None:
            self._task.cancel()

    def _exit(self) -> None:
        self._state.running = False
        # Çalışan tur uygulamayla birlikte KABA iptal edilmesin: önce görev iptal edilir,
        # alt süreçler (shell, MCP) kendi temizliğini yapabilsin (L2-24).
        if self._busy and self._task is not None:
            self._task.cancel()
        self._queue.clear()
        self._tui.request_exit()

    def _cycle(self) -> None:
        self._state.cycle_approval()
        self._sync_status()

    @property
    def _busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def _sync_status(self) -> None:
        vim = bool(getattr(self._state.config.runtime, "vim_mode", False))
        self._tui.set_vim(vim)
        self._tui.set_status(
            self._state.approval.value,
            self._state.engine.value,
            status_view.context_label(self._state),
            self._custom_status,
            vim=vim,
        )
        # Tuş dosyası değiştiyse yeniden başlatmadan uygula (P-067).
        if keybindings.has_changed(self._tui.keymap):
            self._tui.rebind(keybindings.load_keymap(self._tui.keymap.path))

    async def _refresh_custom_status(self) -> None:
        """Kullanıcı betiği (P-069) tur sonunda bir kez çalışır; sonucu durum satırına gider."""
        self._custom_status = await status_line.status_line_text(self._state)
        self._sync_status()

    def _echo(self, renderable: object) -> None:
        """Konuşmaya bir şey yaz ve ekranı tazele."""
        self._out.print(renderable)
        self._tui.sync_conversation()

    def _refresh_config(self) -> None:
        """Turdan önce kontrol paneli değişikliklerini al (satır-içi yolla aynı, L2-06)."""
        if self._state.refresh_config():
            self._sync_status()
            self._echo(
                f"[{theme.DIM}]Kontrol paneli ayarları yüklendi · "
                f"{escape(self._state.config.agent.model)} · "
                f"config {self._state.config_revision.value}[/{theme.DIM}]"
            )
        if config_error := self._state.take_config_error():
            self._echo(
                f"[{theme.WARN}]"
                f"{escape(messages.REPL_CONFIG_UNREADABLE.format(error=config_error))}"
                f"[/{theme.WARN}]"
            )

    def _arm_reminders(self) -> None:
        """`/schedule` ile kurulan hatırlatmaları arka plana al; süresi dolunca göster."""
        for reminder in self._state.reminders:
            self._background.spawn(self._remind(reminder))
        self._state.reminders.clear()

    async def _remind(self, reminder: Reminder) -> None:
        await asyncio.sleep(reminder.due_in_seconds)
        self._echo(f"[{theme.WARN}]{escape(reminder.text)}[/{theme.WARN}]")

    async def _handle(self, line: str) -> None:
        try:
            self._refresh_config()
            self._transcript_store.record_user(line)
            ConsoleRenderer(self._out).print_user_message(line)
            self._tui.sync_conversation()
            line = skill_prefix_to_slash(line, self._registry.is_dynamic)
            # Önekler (P-022): satır-içi yolla aynı fonksiyonlar (`loop.py`).
            if (shell := prefixes.shell_command(line)) is not None:
                await run_shell_prefix_line(shell, self._state, self._out)
                self._tui.sync_conversation()
            elif (note := prefixes.memory_note(line)) is not None:
                self._echo(
                    f"[{theme.DIM}]{escape(prefixes.add_memory_note(self._state, note))}"
                    f"[/{theme.DIM}]"
                )
            elif is_command_line(line):
                await self._command(line)
            else:
                for mention_note in apply_mentions(line, self._state):
                    self._echo(f"[{theme.DIM}]{escape(mention_note)}[/{theme.DIM}]")
                await self._turn(line)
                await self._refresh_custom_status()
        except asyncio.CancelledError:
            self._echo(f"[{theme.WARN}]{messages.REPL_TURN_CANCELLED}[/{theme.WARN}]")
            # Kullanıcı durdurmak istedi: kuyruktaki sıradaki iş HEMEN başlamaz (L2-24).
            # Ölçüldü (30 Ekim): `finally` kuyruğu çalıştırıyor, Esc'e basan kullanıcının
            # durdurmak istediği yerde bir sonraki mesaj başlıyordu. Düşen satırlar söylenir.
            if self._queue:
                dusen = len(self._queue)
                self._queue.clear()
                self._echo(
                    f"[{theme.DIM}]{messages.TUI_QUEUE_DROPPED.format(count=dusen)}[/{theme.DIM}]"
                )
        except Exception as error:
            _logger.exception("TUI turu beklenmeyen hatayla bitti")
            # Ayrıntı kullanıcıya da gösterilir: yalnız "hata" yazmak sebebi saklıyordu (L2-24).
            self._echo(
                f"[{theme.ERROR}]{theme.ICON_ERROR} {messages.ERROR_PREFIX}[/{theme.ERROR}] "
                f"{escape(summarize_error(str(error) or type(error).__name__))}"
            )
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
        if command.name in ASYNC_COMMANDS:
            await remote_control.run(self._state, argument, self._out)
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
        elif command.name == "theme" and not argument.strip():
            selected = await self._tui.await_choice(
                messages.THEME_TITLE, view_commands.theme_choices(self._state)
            )
            if selected is None:
                self._echo(f"[{theme.DIM}]{messages.PICKER_CANCELLED}[/{theme.DIM}]")
                return
            argument = selected
        elif command.name == "search":
            # Arama yalnız tam ekranda anlamlı (P-070): konuşma tamponu buradadır.
            needle = argument.strip()
            if not needle:
                self._echo(f"[{theme.DIM}]{messages.SEARCH_USAGE}[/{theme.DIM}]")
                return
            count = self._tui.scroll_to_match(needle)
            text = (
                messages.SEARCH_FOUND.format(text=needle, count=count)
                if count
                else messages.SEARCH_NOT_FOUND.format(text=needle)
            )
            self._echo(f"[{theme.DIM}]{escape(text)}[/{theme.DIM}]")
            return
        elif command.name == "output-style" and not argument.strip():
            # Çıktı stili (P-068): uygulama-içi modalla seç, seçileni argüman yap.
            selected = await self._tui.await_choice(
                messages.OUTPUT_STYLE_TITLE, output_style_command.style_choices(self._state)
            )
            if selected is None:
                self._echo(f"[{theme.DIM}]{messages.PICKER_CANCELLED}[/{theme.DIM}]")
                return
            argument = selected
        elif command.name == "development":
            # İki adımlı (kaynak→model) seçim: nested prompt_toolkit seçicisi TUI'yi
            # bozardı; uygulama-içi modalla sürülür. Argüman verilse bile modal açılır.
            await self._run_development()
            return
        elif command.name == "resume" and not argument.strip():
            # Fusion'ın kendi sohbetleri: aynı modal deseni, liste transcript deposundan.
            resolved = await self._resolve_own_resume()
            if resolved is None:
                return
            argument = resolved
        elif command.name == "rewind":
            resolved = await self._resolve_rewind_argument(argument)
            if resolved is None:
                return
            argument = resolved
        elif command.name.startswith("resume") and not argument.strip():
            # `/resume<kaynak>` argümansız çağrıldığında düz REPL `pick()` açardı —
            # nested prompt_toolkit seçicisi burada da TUI'yi bozardı. Bunun yerine
            # aynı `mode`/`level`/`effort` deseni: uygulama-içi modal seçtirir,
            # seçilen session_id ARGÜMAN yapılır ve aşağıdaki ortak çağrı üzerinden
            # aynı işleyici (`commands._resume`) çalışır — o da dolu argümanla
            # seçici hiç açmaz.
            resolved = await self._resolve_resume_argument(command.name)
            if resolved is None:
                return
            argument = resolved
        elif command.name == "provider":
            await self._apply_flow(
                lambda picker: provider_flow.choose_provider(self._state.config, picker=picker)
            )
            return
        elif command.name == "verify":
            await self._apply_flow(
                lambda picker: verify_flow.choose_verification(
                    self._state.config, self._state.root, picker=picker
                )
            )
            return
        elif command.name == "profiles" and _profile_edit_target(argument) is not None:
            tier_name, show_incompatible = _profile_edit_target(argument) or ("", False)
            await self._apply_flow(
                lambda picker: profiles_flow.edit_profile_primary(
                    self._state.config,
                    tier_name,
                    picker=picker,
                    show_incompatible=show_incompatible,
                )
            )
            return
        elif _would_open_picker(command.name, argument):
            # Nested picker açacak komutlar TUI'yi bozuyordu; bu görünümde argümanla kullanılır.
            self._echo(
                f"[{theme.DIM}]{messages.TUI_PICKER_NEEDS_ARG.format(name=command.name)}[/{theme.DIM}]"
            )
            return
        result = command.handler(self._state, argument)
        if command.name == "theme":
            self._tui.refresh_style()
        if result:
            self._echo(f"[{theme.DIM}]{escape(result)}[/{theme.DIM}]")
        self._sync_conversation_binding()
        self._arm_reminders()
        self._sync_status()
        if not self._state.running:
            return
        pending, mode = self._state.take_pending()
        if pending:
            await self._turn(pending, mode=mode)

    async def _apply_flow(
        self, flow: Callable[[model_flows.Picker], model_flows.FlowResult]
    ) -> None:
        """Seçici alan bir akışı uygulama-içi modalla sür ve sonucunu uygula.

        Akışlar eşzamanlı bir `picker` bekler (nested prompt_toolkit TUI'yi bozardı).
        İlk geçişte seçenekler yakalanır, modalda seçtirilir, ikinci geçişte seçilen
        değer hazır bir seçici olarak verilir. Seçici hiç çağrılmazsa (zaten kurulu,
        bulunamadı…) ilk geçişin sonucu doğrudan kullanılır.
        """
        captured: list[tuple[Sequence[Choice], str]] = []

        def probe(choices: Sequence[Choice], *, title: str = "", **_: object) -> str | None:
            captured.append((choices, title))
            return None

        result = flow(probe)
        if captured:
            choices, title = captured[0]
            selected = await self._tui.await_choice(title, list(choices))
            result = flow(lambda *_a, **_k: selected)
        self._state.config = result.config
        self._echo(f"[{theme.DIM}]{escape(result.message)}[/{theme.DIM}]")
        self._sync_status()

    def _sync_conversation_binding(self) -> None:
        """Komut sohbet kimliğini (`/resume`, `/branch`) ya da kökü (`/worktree`) değiştirdiyse
        transcript deposunu yeniden bağla; yoksa yeni turlar eski sohbete yazılırdı."""
        store = self._transcript_store
        if store.session_id == self._state.conversation_id and store.root == self._state.root:
            return
        self._transcript_store = TranscriptStore(
            self._state.config.memory_dir,
            self._state.root,
            conversation_id=self._state.conversation_id,
        )

    async def _resolve_rewind_argument(self, argument: str) -> str | None:
        """`/rewind` için eksik parçaları (tur, kapsam) uygulama-içi modalla tamamla.

        Dönen metin tam argümandır (`"3 kod"`); işleyici onu seçici açmadan uygular.
        Vazgeçilirse ya da geri sarılacak tur yoksa `None` döner.
        """
        entries = self._state.checkpoints.entries()
        if not entries:
            self._echo(f"[{theme.DIM}]{messages.REWIND_NOTHING}[/{theme.DIM}]")
            return None
        index, scope, error = rewind.parse_arguments(argument, self._state.checkpoints)
        if error:
            self._echo(f"[{theme.WARN}]{escape(error)}[/{theme.WARN}]")
            return None
        if index is None:
            picked = await self._tui.await_choice(
                messages.REWIND_PICK_TURN, rewind.turn_choices(entries)
            )
            if picked is None:
                self._echo(f"[{theme.DIM}]{messages.PICKER_CANCELLED}[/{theme.DIM}]")
                return None
            index = int(picked)
        if scope is None:
            chosen = await self._tui.await_choice(
                messages.REWIND_PICK_SCOPE, rewind.scope_choices()
            )
            if chosen is None:
                self._echo(f"[{theme.DIM}]{messages.PICKER_CANCELLED}[/{theme.DIM}]")
                return None
            return f"{index} {chosen}"
        return f"{index} {scope.value}"

    async def _resolve_own_resume(self) -> str | None:
        """`/resume` (Fusion sohbetleri) için uygulama-içi seçim; vazgeçilirse `None`."""
        refs = list_conversations(self._state.config.memory_dir, self._state.root)
        if not refs:
            self._echo(f"[{theme.DIM}]{messages.SESSION_LIST_EMPTY}[/{theme.DIM}]")
            return None
        selected = await self._tui.await_choice(
            messages.SESSION_PICK_TITLE, session_resume.resume_choices(refs)
        )
        if selected is None:
            self._echo(f"[{theme.DIM}]{messages.PICKER_CANCELLED}[/{theme.DIM}]")
            return None
        return selected

    async def _resolve_resume_argument(self, command_name: str) -> str | None:
        """`/resume<kaynak>` için uygulama-içi seçim (nested picker YERİNE).

        Kaynak adı komut adının `resume` önekinden sonrasıdır (`resumeclaude` →
        `claude`). Seçilen `session_id` döner; vazgeçilirse ya da devralınacak
        oturum yoksa `None` döner ve çağıran turu burada keser.
        """
        source_name = command_name.removeprefix("resume")
        source = source_by_name(self._state.home, source_name)
        refs = source.list(self._state.root, limit=RESUME_LIST_LIMIT) if source is not None else ()
        if not refs:
            self._echo(f"[{theme.DIM}]{messages.HISTORY_EMPTY}[/{theme.DIM}]")
            return None
        selected = await self._tui.await_choice(messages.HISTORY_PICK_TITLE, resume_choices(refs))
        if selected is None:
            self._echo(f"[{theme.DIM}]{messages.PICKER_CANCELLED}[/{theme.DIM}]")
            return None
        return selected

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
            self._tui.console.print(
                f"[{theme.ACCENT}]{messages.DEV_CUSTOM_PROMPT}[/{theme.ACCENT}]"
            )
            self._tui.sync_conversation()
            model_id: str | None = (await self._tui.await_text()).strip() or None
        else:
            # Ağdan katalog senkron bir çağrıdır; TUI döngüsünü dondurmasın (L2-13).
            entries = await asyncio.to_thread(source.fetcher)
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

        result = await asyncio.to_thread(
            model_flows.apply_development_model, config, model_id, paid=source.paid
        )
        self._state.config = result.config
        self._echo(f"[{theme.DIM}]{escape(result.message)}[/{theme.DIM}]")
        self._sync_status()

    async def _turn(self, line: str, *, mode: macros.Mode = macros.Mode.NONE) -> None:
        """Turu çalıştır. Makro kipi turun ÜÇ ayarını birden belirler.

        Buraya eskiden yalnız `workflow` geçiyordu; `/goal` çağrıldığında kipin
        sistem promptu ("pes etme, ask_user ile müdahale iste") ve yükseltilmiş
        adım sınırı (100) sessizce düşüyordu. Düz konsol yüzeyi (`loop.py`)
        üçünü de geçiyordu; iki yüzey ayrışmıştı.
        """
        # `/mode auto` açıksa kademe bu görev için seçilir (satır-içi yolla aynı, L2-06).
        apply_auto_profile(line, self._state, self._out)
        work = WorkLineSink(interrupt_hint=messages.WORK_INTERRUPT_ESC)
        # Satırı TUI çeker (her spinner karesinde), sink itmez: süre böyle akar.
        self._tui.set_work_source(work.render)
        renderer = ConsoleRenderer(
            self._out,
            live_progress=False,
            show_thinking=self._state.show_thinking,
            show_call_details=self._state.engine is Engine.FUSION,
            show_all_answers=self._state.show_all_answers,
        )
        pump = _PumpSink(self._tui.sync_conversation)
        # Kalıcı kullanım günlüğü (P-056) satır-içi yolla aynı biçimde TUI'yi de besler.
        usage_log = self._state.usage_log
        sinks = (
            renderer,
            work,
            self._transcript_store,
            pump,
            self._state.cost,
            *((usage_log,) if usage_log is not None else ()),
        )
        try:
            if self._state.engine is Engine.FUSION:
                # Beceri ekleri bu motorda kullanılmaz; sonraki agent turuna sızmasın.
                self._state.take_pending_extras()
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
                # Bağlam BURADA kurulur ve saklanır: `/undo` turun değişiklik
                # kümesine erişebilmek zorundadır.
                # Tur checkpoint'i: konuşma kopyası + bu turun değişiklik kümesi (`/rewind`).
                checkpoint = self._state.checkpoints.begin(line, self._state.history)
                tool_context = ToolContext(
                    root=self._state.root,
                    extra_roots=self._state.extra_roots,
                    restrict_to_root=self._state.config.runtime.restrict_to_root,
                    browser=browser_session_from(self._state.config),
                    block_reads_outside_root=self._state.config.runtime.block_reads_outside_root,
                    block_writes_outside_root=self._state.config.runtime.block_writes_outside_root,
                    changes=checkpoint.changes,
                )
                # Değişiklik kümesi tur boyunca yerinde dolar; tur kesilse ya da hatayla
                # bitse de `/undo` yarım yazılmış dosyaları geri alabilsin (L2-12).
                self._state.last_changes = tool_context.changes
                partial = PartialTurn()
                # Digest TEK SEFERLİK okunur; bu yüzden yalnız onu gerçekten
                # kullanan agent dalında tüketilir. Kip promptuyla aynı metinde
                # birleşir (`loop.py` ile aynı sıra).
                digest = self._state.take_pending_digest()
                extras = self._state.take_pending_extras()
                turn_extra_system = "\n\n".join(
                    part for part in (macros.mode_prompt(mode), digest, extras.context) if part
                )
                try:
                    outcome = await run_agent_task(
                        line,
                        self._state.config,
                        remotion_transport=self._state.remotion_transport,
                        remotion_browser=self._state.remotion_browser,
                        sinks=sinks,
                        prompter_factory=self._prompter_factory,
                        mode=self._state.approval,
                        task_type=self._state.task_type,
                        root=self._state.root,
                        home=self._state.home,
                        extra_system=turn_extra_system,
                        interactive=True,
                        conversation_id=self._state.conversation_id,
                        memory=self._state.memory,
                        history=self._state.history,
                        health=self._state.health,
                        capabilities=self._state.capabilities,
                        journal=partial,
                        background=self._background,
                        tool_context=tool_context,
                        approval_memory=self._state.approval_memory,
                        step_limit=macros.mode_step_limit(mode),
                        workflow=macros.mode_workflow(mode),
                        allowed_tools=extras.merged_tools(None),
                    )
                except (asyncio.CancelledError, Exception):
                    # İptal/hata: o turun araç sonuçları geçmişten düşmesin (L2-12).
                    self._state.history = partial.history_after_interruption(
                        previous=self._state.history, task=line, root=self._state.root
                    )
                    # Tüketilen devralma künyesi tur başarısızsa KAYBOLMAZ: bir sonraki
                    # tur yeniden alır (L2-24).
                    if digest and not self._state.pending_digest:
                        self._state.pending_digest = digest
                    raise
                self._state.history = outcome.messages
                # Onay kartındaki "bir daha sorma" kuralı yazıldı/yazılamadı bildirimi (P-003).
                # Ölçüldü (31 Ekim): yalnız düz konsol döngüsü basıyordu, TUI hiç göstermiyordu.
                print_rule_notices(self._tui.console, self._state.approval_memory)
                # `enter_worktree`/`exit_worktree` isteği tur bitince uygulanır.
                switched = worktrees.apply_switch(self._state, tool_context)
                if switched:
                    self._echo(f"[{theme.DIM}]{escape(switched)}[/{theme.DIM}]")
                    self._sync_conversation_binding()
        finally:
            renderer.abort()
            self._tui.clear_work()
            self._tui.sync_conversation()


def _print_startup(
    session: _TuiSession, state: ReplState, resume: session_resume.ResumeTarget | None = None
) -> None:
    """Açılış kutusunu ve varsa son oturum listesini konuşma alanına yaz.

    Liste boşsa (kayıtlı oturum yoksa) hiçbir şey basılmaz — düz konsol
    yüzeyindeki `history_view.render_recent` davranışıyla birebir aynı kural.
    """
    from .loop import apprentice_switch_notice, session_info

    banner.print_welcome(session.tui.console, session_info(state), clear=False, pad=False)
    if resume is not None:
        session.tui.console.print(
            f"[{theme.DIM}]{escape(session_resume.launch_notice(resume))}[/{theme.DIM}]"
        )
    bildirim = apprentice_switch_notice(state.config)
    if bildirim:
        session.tui.console.print(bildirim)
    if has_untrusted_permissions(state.root):
        session.tui.console.print(f"[{theme.WARN}]{messages.PERMISSIONS_UNTRUSTED}[/{theme.WARN}]")
    recent = history_view.render_recent(state.home, state.root)
    if recent:
        session.tui.console.print(recent, highlight=False)
    session.tui.sync_conversation()


async def run_tui_repl(
    state: ReplState, console: Console, *, resume: session_resume.ResumeTarget | None = None
) -> int:
    """Ink-benzeri tek yol REPL'i çalıştır. Çıkış kodunu döndürür."""
    session = _TuiSession(state)
    # Açılış kutusu konuşma alanına yazılır (tam-ekranda üstte durur).
    _print_startup(session, state, resume)

    # TUI isolation: ana terminal scrollback + ekranı temizle. macOS Terminal.app
    # ED 3'ü (`\x1b[3J`) desteklemez ve bunu sessizce yok sayar; oradaki asıl
    # koruma tekerleği uygulamaya yönlendiren kiplerdir (bkz. tui._apply_wheel_modes).
    sys.stdout.write("\x1b[3J\x1b[2J\x1b[H")
    sys.stdout.flush()
    try:
        await session.tui.application.run_async()
    finally:
        # Kipler terminal geneline yazılır; fusion çıkınca terminal normale dönmeli.
        session.tui.restore_wheel_modes()

    # Bekleyen arka plan işlerini (ders çıkarımı) bitir; hataları yut ma, log'la.
    await remote_control.shutdown(state)
    await session.background.drain()
    for failure in session.background.failures:
        _logger.warning("arka plan işi başarısız: %s", failure)

    # Çıkışta konuşmayı gerçek terminale dök: tam-ekran kapanınca scrollback kaybolmasın.
    sys.stdout.write(session.tui.transcript)
    sys.stdout.flush()
    return 0

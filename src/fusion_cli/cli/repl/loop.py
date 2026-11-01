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
import logging
import os
import signal
import sys
import time
from collections.abc import Awaitable, Callable, Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar, cast

from rich.console import Console
from rich.markup import escape

from ...core.remotion_browser import RemotionBrowser
from ...tools import desktop_turn
from ...tools.remotion_observe import browser_transport
from .. import launch_prompts as launch_prompts_mod

if TYPE_CHECKING:
    from ...engines.agent.loop import AgentDeps, AgentOutcome
    from ...engines.agent.remotion_bridge import FrameTransport
    from ...tools.registry import ToolRegistry

from ...config import model_select, profile
from ...config.apprentice_notice import apprentice_notice_shown, mark_apprentice_notice_shown
from ...config.models import Config
from ...config.permission_warnings import skipped_rule_warnings
from ...config.permissions import has_untrusted_permissions
from ...core.changeset import ChangeSet
from ...core.concurrency import BackgroundTasks
from ...core.events import (
    ErrorOccurred,
    EventPublisher,
    FilesChanged,
    FollowupsSuggested,
    NoFileChanges,
    TurnFinished,
)
from ...core.followups import suggest_followups
from ...core.hooks.events import HookEvent
from ...core.session_cron import Source
from ...core.session_goal import GoalVerdict
from ...core.tools import ToolContext
from ...core.types import FusionResult, Message
from ...core.worktree import Worktree
from ...engines.agent import skill_grants
from ...engines.agent.compaction import compress
from ...engines.agent.goal_judge import GoalJudgement, judge_goal
from ...engines.agent.hook_text import context_reminder
from ...engines.agent.turn_evidence import evidence_from_turn
from ...engines.hooks.notify import notifying
from ...memory.factory import Memory
from ...observability.bus import EventBus
from ...observability.tracing import LangfuseTracer
from ...observability.usage_log import open_usage_log
from ...providers.capabilities import apprentice_active
from ...providers.health_setup import build_health
from ...tools.capabilities import Capability
from ...ui import banner, messages, theme
from ...ui.renderer import ConsoleRenderer
from ...ui.text import summarize_error
from ..desktop_never import AppDenials, config_persist
from ..mcp_notice import new_failure_lines
from ..prompter import ConsolePrompter
from ..rule_notices import print_rule_notices
from . import (
    agent_link,
    async_commands,
    browser_command,
    chrome_cli,
    cron_store,
    goal_flow,
    goal_store,
    help_view,
    history_view,
    hook_events,
    linked_pr,
    loop_command,
    macros,
    persona_commands,
    plan_card,
    prefixes,
    remote_control,
    session_agent,
    session_resume,
    status_line,
    view_commands,
    worktrees,
)
from .background_commands import interrupted_to_background, route_at_message
from .commands import (
    ASYNC_COMMANDS,
    CommandRegistry,
    build_registry,
    is_command_line,
    parse,
    renders_itself,
)
from .completion import agent_names
from .hook_open import open_hooks
from .inline_keys import (
    BackgroundKey,
    background_key_action,
    prompt_pause,
    session_keys,
    take_typed_line,
    take_typed_partial,
)
from .input import ReplInput
from .macros import Mode
from .partial_turn import PartialTurn
from .persona_commands import persona_turn
from .state import Engine, Reminder, ReplState

#: `_cancel_on_interrupt` her sonuç tipindeki görevi kesebilir (tur, hedef değerlendirmesi).
ResultT = TypeVar("ResultT")

#: Komut geçmişinin saklandığı dosya adı.
HISTORY_FILE = "repl_history"

_logger = logging.getLogger(__name__)


def apprentice_switch_notice(config: Config) -> str | None:
    """Faz 3, Görev 2 (§6.1): agent web'e kilitliyse TEK SEFERLİK açılış bildirimi.

    Yalnızca BİLGİLENDİRİR; hiçbir yapılandırmayı sessizce değiştirmez. Kullanıcı
    `/level cirak` ile dönebilir. Bildirim kalıcı bir işaretle bir daha çıkmaz
    (`config/apprentice_notice.py`); işaret bu çağrının YAN ETKİSİDİR — metni
    gösterip göstermeyeceğine çağıran karar verir ama işaret burada konur.
    """
    if apprentice_active(config) or apprentice_notice_shown():
        return None
    mark_apprentice_notice_shown()
    tier = config.tier_by_name(model_select.APPRENTICE_TIER_NAME)
    onerilen = tier.agent.model if tier is not None else "?"
    return messages.APPRENTICE_SWITCH_NOTICE.format(model=config.agent.model, onerilen=onerilen)


def is_interactive_terminal() -> bool:
    """stdin ve stdout ikisi de terminal mi? (TUI yalnız o zaman kurulur.)"""
    return sys.stdin.isatty() and sys.stdout.isatty()


async def run_repl(
    config: Config,
    *,
    memory: Memory,
    root: Path,
    console: Console,
    extra_roots: tuple[Path, ...] = (),
    remotion_transport: FrameTransport | None = None,
    remotion_browser: RemotionBrowser | None = None,
    persona: str = "",
    session_agents: tuple[Capability, ...] = (),
    resume: session_resume.ResumeTarget | None = None,
    worktree: Worktree | None = None,
    initial_prompt: str = "",
    launch_prompts: object = None,
    setup_trigger: str = "",
    chrome: bool | None = None,
) -> int:
    """İnteraktif oturumu çalıştır. Çıkış kodunu döndürür.

    `setup_trigger` (`fusion --init` / `--maintenance`): `Setup` kancası SessionStart'tan önce.

    `resume` verilirse (`--continue/--resume/--name`) oturum o sohbetin kimliğine ve
    geçmişine bağlı açılır; verilmezse her açılış yeni bir sohbettir. `worktree`
    verilirse (`--worktree`) `root` o ağaçtır; çıkışta temiz ağaç kaldırılır.

    `persona` (`fusion --agent <ad>`, P-053) oturumu o ajan tanımıyla açar; ad
    bulunamazsa açılmadan 1 ile çıkar — sessizce varsayılana düşmek kullanıcıyı yanıltır.
    """
    # Varsayılan: Ink-benzeri tek yol TUI (Claude Code modeli). Eski satır-içi mod yalnızca
    # acil yedek olarak FUSION_INLINE=1 ile açılır; TUI kararlılığı doğrulanınca kaldırılacak
    # (bkz. docs/BACKLOG.md). Borulu/CI kullanımı (`echo /help | fusion`) tam-ekran
    # uygulamaya düşmemeli: stdin ya da stdout terminal değilse satır-içi yola geçilir.
    # Kayıtlı motor ve izin modu (`runtime.engine`/`approval_mode`) iki yolda da uygulanır.
    state = ReplState.from_runtime_config(
        config,
        memory=memory,
        root=root,
        home=Path.home(),
        session_agents=session_agents,
        extra_roots=extra_roots,
        remotion_transport=remotion_transport,
        remotion_browser=remotion_browser,
        health=build_health(config),
        worktree=worktree,
    )
    # Kalıcı kullanım günlüğü oturum boyunca yaşar; `/usage` pencereleri bundan okur (P-056).
    state.usage_log = open_usage_log(config)
    restored_note = ""
    if resume is not None:
        session_resume.apply_target(state, resume)
        if not persona.strip():
            # Claude Code: sürdürülen oturum kendi ajanıyla açılır (#16).
            restored_note = session_agent.restore(state)
            if restored_note:
                console.print(f"[{theme.WARN}]{escape(restored_note)}[/{theme.WARN}]")
    try:
        # `--chrome`/`--no-chrome`/Enabled by default (#421): köprü oturum boyu yaşar.
        state.chrome = await chrome_cli.open_for_session(
            console,
            root=root,
            home=state.home,
            flag=chrome,
            interactive=is_interactive_terminal(),
        )
        requested_persona = persona.strip() or (
            ""
            if resume is not None and (state.persona or restored_note)
            else config.agent_launch.default_agent
        )
        if requested_persona:
            notice = persona_commands.persona(state, requested_persona)
            if state.persona is None:
                console.print(f"[{theme.WARN}]{escape(notice)}[/{theme.WARN}]")
                return 1
            console.print(f"[{theme.INFO}]{escape(notice)}[/{theme.INFO}]")
            if (
                state.persona is not None
                and state.persona.initial_prompt.strip()
                and not state.history
            ):
                state.pending_task = state.take_persona_initial("")
        # `fusion "istem"` (Claude `claude "query"`, #276): yüzey açılınca ilk tur.
        state.initial_prompt = initial_prompt.strip()
        state.launch_prompts = launch_prompts_mod.bind(state, launch_prompts, resumed=resume)
        return await _run_surface(state, config, console, resume, setup_trigger)
    finally:
        await chrome_cli.close_session(state.chrome)
        await state.child_runs.close()
        if state.hook_session is not None:
            await state.hook_session.end("prompt_input_exit")
        # `--worktree`: oturum bitince temiz ağaç kaldırılır, iş kalmışsa yolu söylenir.
        if worktree is not None and state.worktree is not None:
            console.print(
                f"[{theme.DIM}]{escape(worktrees.leave_session_worktree(state))}[/{theme.DIM}]"
            )


async def _run_surface(
    state: ReplState,
    config: Config,
    console: Console,
    resume: session_resume.ResumeTarget | None,
    setup_trigger: str = "",
) -> int:
    """Yüzeyi seç (TUI ya da satır-içi) ve çalıştır."""
    # Terminal paleti oturum başında (P-070): tüm yüzeyler `theme.X`'i çağrı anında okur.
    view_commands.apply_theme_setting(state)
    # Claude: SessionStart oturum açılırken çalışır (ilk istem beklenmez, #111).
    await open_hooks(state, console, setup_trigger=setup_trigger)
    inline_requested = (
        os.environ.get("FUSION_INLINE") == "1" or getattr(config.runtime, "tui", "") == "inline"
    )
    if not inline_requested and is_interactive_terminal():
        from .tui_loop import run_tui_repl

        # Sürdürme bilgisi yalnız varsa geçirilir: TUI giriş noktasının eski çağrı
        # biçimi (state, console) ve onu taklit eden testler aynen çalışmaya devam eder.
        if resume is None:
            return await run_tui_repl(state, console)
        return await run_tui_repl(state, console, resume=resume)

    # Ev dizini GEÇİLİR: dinamik `/resume<kaynak>` komutları ancak böyle kaydolur.
    # Argümansız çağrı bu yüzeyi sessizce komutsuz bırakıyordu.
    registry = build_registry(state.home, skills=lambda: state.capabilities)
    # Sözlük çağrılabilir verilir: `/skills reload` ya da `/add-dir` sonrası yeni beceri
    # komutları Tab tamamlamada da görünsün (dinamik defter, P-019).
    reader = ReplInput(
        config.memory_dir / HISTORY_FILE,
        registry.completion_words,
        mode=state.approval,
        roots=lambda: (state.root, *state.extra_roots),
        agents=lambda: agent_names(state),
    )
    # Satır içi yedek girişte de Shift+Tab döngüsü TUI ile aynı kipleri içerir (#73, #85).
    reader.bypass_available = bool(getattr(state, "bypass_available", False))
    reader.auto_available = bool(getattr(state, "auto_available", True))
    background = BackgroundTasks()

    # Isıtma kota harcar ve kullanıcı henüz bir şey göndermeden kafa karıştırıcı
    # sağlayıcı hataları basabilir. Örtük çağrı yerine açık opt-in tutulur
    # (FUSION_WARMUP=1). Kapalıyken ilk tur biraz daha yavaş başlar ama beklenmedik
    # hata gürültüsü olmaz.
    if os.environ.get("FUSION_WARMUP", "0").strip().lower() in {"1", "true", "yes", "on"}:
        background.spawn(_warm_up(state))

    reader.vim_mode = bool(getattr(state.config.runtime, "vim_mode", False))
    banner.print_welcome(console, session_info(state))
    if resume is not None:
        console.print(f"[{theme.DIM}]{session_resume.launch_notice(resume)}[/{theme.DIM}]")
    bildirim = apprentice_switch_notice(state.config)
    if bildirim:
        console.print(bildirim)
        console.print()
    if has_untrusted_permissions(state.root):
        console.print(f"[{theme.WARN}]{messages.PERMISSIONS_UNTRUSTED}[/{theme.WARN}]")
    # Dış `@import` ilk görüldüğünde onay (Claude Code #145).
    from ...engines.agent import import_approval

    await import_approval.offer(
        state.root,
        state.home,
        show=lambda text: console.print(escape(text), highlight=False),
        read_answer=reader.prompt,
        extra_roots=tuple(state.extra_roots),
    )
    for uyari in skipped_rule_warnings(state.root):
        console.print(f"[{theme.WARN}]{uyari}[/{theme.WARN}]", highlight=False)
    recent = history_view.render_recent(state.home, state.root)
    if recent:
        console.print(recent, highlight=False)
        console.print()
    _sync_status_bar(reader, state, background)
    state.cron = cron_store.load(state.config.memory_dir, state.conversation_id)
    # `--resume` ile açılan sohbetin hedefi geri gelir (P-058).
    state.goal = goal_store.load(state.config.memory_dir, state.conversation_id)
    # Gözcü arka plan iş yöneticisine GİRMEZ: `drain()` onu da beklerdi ve EOF ile biten
    # oturum hiç kapanmazdı. Sahibi bu döngüdür; çıkışta iptal edilir.
    cron_watcher = asyncio.ensure_future(_cron_watcher(state, reader, console))
    # Arka plan görevleri + oturumlar arası mesaj (P-048/P-060): bildirim ve gelen kutusu.
    link_watcher = agent_link.start_watch(
        state,
        kind="repl",
        emit=lambda text: console.print(f"[{theme.DIM}]{escape(text)}[/{theme.DIM}]"),
        inject=reader.inject,
        # Ölçüldü (31 Ekim): `lambda: False` idi; tur sürerken eş listesi "boşta" diyordu.
        is_busy=lambda: bool(handling),
    )
    handling: list[str] = []
    idle_watcher = hook_events.start_idle_watch(
        state,
        lambda: bool(handling),
        lambda text: console.print(f"[{theme.WARN}]{escape(text)}[/{theme.WARN}]"),
    )

    try:
        if state.initial_prompt:
            first, state.initial_prompt = state.initial_prompt, ""
            await _handle_safely(first, state, registry, reader, console, background)
        while state.running:
            line = await _read_line(reader, state)
            if line is None:
                break
            if not line.strip():
                continue
            handling.append(line)
            try:
                await _handle_safely(line.strip(), state, registry, reader, console, background)
            finally:
                handling.clear()
            cron_store.save(state.config.memory_dir, state.conversation_id, state.cron)
    finally:
        cron_watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cron_watcher
        await hook_events.stop_idle_watch(idle_watcher)
        await agent_link.stop_watch(state, link_watcher)
        await remote_control.shutdown(state)
        await browser_command.shutdown(state)
        await _shutdown(background, console)
    return 0


#: Zamanlayıcı vadesi bu sıklıkla yoklanır; görev en az 1 dakikalık olduğundan yeter.
CRON_POLL_S = 1.0


async def _cron_watcher(state: ReplState, reader: ReplInput, console: Console) -> None:
    """Vadesi gelen `/loop`/`cron_*` görevini REPL boştayken yeni satır olarak ver (P-038).

    Tur sürerken ya da istem açık değilken beklenir; görev düşmez. Satır istem
    üzerinden girer (`ReplInput.inject`) ki komut da (`/verify`) görev de aynı yoldan
    işlensin. Ajanın kurduğu görev (`Source.AGENT`) yalnız TUR olur: `_handle` slash
    satırını komut olarak çalıştırmaz (onaysız `cron_create` kip yükseltemesin).
    """
    while state.running:
        await asyncio.sleep(CRON_POLL_S)
        now = time.time()
        due = state.cron.due(now)
        if not due:
            continue
        task = due[0]
        state.scheduled_turn_only = task.source is Source.AGENT
        state.scheduled_fire = True  # zamanlanmış `/beceri` fork'u beklenir (#141)
        if not reader.inject(loop_command.fire_prompt(task)):
            state.scheduled_turn_only = state.scheduled_fire = False
            continue
        state.cron.complete(task.id, now=now)
        console.print(f"[{theme.DIM}]{messages.LOOP_FIRED.format(id=task.id)}[/{theme.DIM}]")
        cron_store.save(state.config.memory_dir, state.conversation_id, state.cron)


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
    from ...providers.web_registry import web_registry_for

    request = CompletionRequest(
        messages=(Message("user", "hi"),),
        temperature=state.config.runtime.judge_temperature,
        max_tokens=1,
        timeout_s=state.config.runtime.request_timeout_s,
        max_retries=0,
    )
    # Sessiz sağlayıcı: ısıtma ne gösterilir ne de muhasebeye girer (1 token).
    #
    # Web oturum kaydı BURADA DA geçilir. Geçilmediğinde, agent modeli bir web
    # oturumuysa ısıtma var olmayan bir uca gidiyor, hata yutuluyor ve ısıtma
    # hiç gerçekleşmiyordu. Tarayıcı taşımasında ısıtmanın değeri daha da büyük:
    # ilk mesajın beklediği asıl gecikme oturumun açılmasıdır.
    try:
        await build_provider(
            state.config.agent,
            publisher=None,
            retry_delays_s=state.config.runtime.retry_delays_s,
            web_sessions=web_registry_for(state.config),
        ).complete(request)
    except Exception:
        # Belgenin söylediği gibi sessiz: aksi hâlde hata `background.failures`a düşüp
        # çıkışta "arka plan: …" diye basılıyordu (L2-26).
        _logger.debug("ısıtma çağrısı başarısız", exc_info=True)


async def _read_line(reader: ReplInput, state: ReplState) -> str | None:
    """Kullanıcıdan satır al. Ctrl-D/EOF'ta None döner (çıkış)."""
    typed = take_typed_line(state)
    if typed is not None:
        # Tur sürerken yazılıp Enter'lanan satır sıradaki mesajdır (Claude Code kuyruğu, #12).
        return typed
    try:
        default = state.take_pending_input() + take_typed_partial(state)
        line = await reader.prompt(default=default)
    except (EOFError, KeyboardInterrupt):
        return None
    # shift-tab girişte modu değiştirmiş olabilir; durumu senkronla.
    state.approval = reader.mode
    return line


async def _handle_safely(
    line: str,
    state: ReplState,
    registry: CommandRegistry,
    reader: ReplInput,
    console: Console,
    background: BackgroundTasks,
) -> None:
    """`_handle`ı çalıştır; komut işleyicisi ya da motor hatası REPL'i bitirmesin.

    Ölçüldü (30 Ekim): yalnız `CancelledError` yakalanıyordu; bir komut işleyicisindeki
    `OSError` ya da motor hatası döngüyü sonlandırıp kullanıcıyı REPL'den atıyordu
    (TUI yolunda genel yakalama zaten vardı; L2-26).
    """
    try:
        await _handle(line, state, registry, reader, console, background)
    except Exception as error:
        _logger.exception("REPL satırı beklenmeyen hatayla bitti")
        console.print(
            f"[{theme.ERROR}]{theme.ICON_ERROR} {messages.ERROR_PREFIX}[/{theme.ERROR}] "
            f"{escape(summarize_error(str(error) or type(error).__name__))}"
        )


async def _handle(
    line: str,
    state: ReplState,
    registry: CommandRegistry,
    reader: ReplInput,
    console: Console,
    background: BackgroundTasks,
) -> None:
    if state.refresh_config():
        reader.mode = state.approval
        _sync_status_bar(reader, state, background)
        console.print(
            f"[{theme.DIM}]Kontrol paneli ayarları yüklendi · "
            f"{state.config.agent.model} · config {state.config_revision.value}[/{theme.DIM}]"
        )
    if config_error := state.take_config_error():
        console.print(
            f"[{theme.WARN}]{escape(messages.REPL_CONFIG_UNREADABLE.format(error=config_error))}"
            f"[/{theme.WARN}]"
        )
    if state.welcome_padded:
        # Açılış dolgusu konuşmanın ortasında dev bir boşluğa dönüşmesin.
        banner.print_welcome(console, session_info(state), pad=False)
        state.welcome_padded = False
    ConsoleRenderer(console).print_user_message(line)
    # Ajanın zamanladığı satır komut ya da önek DEĞİL turdur (bkz. `_cron_watcher`).
    scheduled_turn = state.take_scheduled_turn_only()
    if not scheduled_turn:
        # Önekler (P-022): `!` kabuk ve `#` not model çağırmaz; `@dosya` bağlama eklenir.
        if (shell := prefixes.shell_command(line)) is not None:
            await run_shell_prefix_line(shell, state, console)
            _sync_status_bar(reader, state, background)
            return
        if (note := prefixes.pending_memory_note(state, line)) is not None:
            # `# not` düz metin belleğe yazılır (Claude Code kısayolu, P-036); bellek
            # kapalıysa satır olağan istemdir.
            console.print(
                f"[{theme.DIM}]{escape(prefixes.add_memory_note(state, note))}[/{theme.DIM}]"
            )
            return
    if is_command_line(line) and not scheduled_turn:
        await _run_command(line, state, registry, reader, console)
        # Makrolar görev HAZIRLAR, çalıştırmaz: komut işleyicileri saf ve senkron
        # kalsın diye çalıştırma buraya bırakılmıştır.
        _arm_reminders(state, console, background)
        task, mode = state.take_pending()
        if task:
            if await _run_turn(task, state, console, background, mode=mode):
                await _continue_goal(state, console, background)
            await _offer_plan_card(state, console, background, reader)
            # Tur bir arka plan ders çıkarımı BAŞLATMIŞ olabilir; bir sonraki
            # istemde sayaç GÜNCEL görünsün (bkz. `_sync_status_bar`).
            _sync_status_bar(reader, state, background)
        return
    # `@oturum mesaj` / `@görev mesaj` (P-060): tur değil, mesaj gönderimi.
    if not scheduled_turn and (sent := route_at_message(state, line)) is not None:
        console.print(f"[{theme.DIM}]{escape(sent)}[/{theme.DIM}]")
        return
    for note in apply_mentions(line, state):
        console.print(f"[{theme.DIM}]{escape(note)}[/{theme.DIM}]")
    if await _run_turn(line, state, console, background):
        await _continue_goal(state, console, background)
    await _offer_plan_card(state, console, background, reader)
    _sync_status_bar(reader, state, background)
    # Kullanıcı betiği (P-069) tur sonunda bir kez çalışır; yerleşik satırın yerine geçer.
    reader.custom_status = await status_line.status_line_text(state)


def apply_mentions(line: str, state: ReplState) -> tuple[str, ...]:
    """`@dosya` anmalarını çöz, blokları bekleyen bağlama ekle; kullanıcı notlarını döndür."""
    result = prefixes.expand_mentions(line, state)
    for block in result.blocks:
        prefixes.push_pending_context(state, block)
    return result.notes


async def run_shell_prefix_line(command: str, state: ReplState, console: Console) -> None:
    """`! komut` satırını çalıştır ve çıktıyı bas; iki REPL yüzeyi bunu paylaşır."""
    console.print(
        f"[{theme.ACCENT}]{escape(messages.SHELL_PREFIX_RUNNING.format(command=command))}"
        f"[/{theme.ACCENT}]",
        highlight=False,
    )
    result = await prefixes.run_shell_prefix(state, command)
    for note in result.notes:
        console.print(f"[{theme.WARN}]{escape(note)}[/{theme.WARN}]")
    if result.output:
        color = theme.DIM if result.ok else theme.ERROR
        console.print(f"[{color}]{escape(result.output)}[/{color}]", highlight=False)
    if result.context_block:
        console.print(f"[{theme.DIM}]{messages.SHELL_PREFIX_CONTEXT_NOTE}[/{theme.DIM}]")


async def _offer_plan_card(
    state: ReplState, console: Console, background: BackgroundTasks, reader: ReplInput
) -> None:
    """Plan kipinde biten turun kabul kartı; kabulde uygulama turu hemen başlar (P-025)."""
    task = await plan_card.offer(state, console, interactive=reader.interactive)
    reader.mode = state.approval
    if task:
        await _run_turn(task, state, console, background)


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

    if renders_itself(command.name, argument):
        await help_view.render(command.name, state, registry, console)
        return
    if command.name in ASYNC_COMMANDS:
        # Ctrl-C uzun süren işi (dikte) keser, REPL'i değil.
        task = asyncio.ensure_future(async_commands.run(command.name, state, argument, console))
        with _cancel_on_interrupt(task):
            try:
                await task
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                cancelled = messages.ASYNC_COMMAND_CANCELLED.format(name=command.name)
                console.print(f"[{theme.WARN}]{cancelled}[/{theme.WARN}]")
        return

    if command.name == "permissions" and not argument.strip() and reader.interactive:
        # Claude (#83): argümansız /permissions sekmeli iletişim kutusunu açar.
        from .permissions_dialog import PlainIO, run_permissions_dialog

        def say(text: str) -> None:
            console.print(f"[{theme.DIM}]{escape(text)}[/{theme.DIM}]")

        say(await run_permissions_dialog(state, PlainIO(say)))
        return

    previous = (state.root, state.conversation_id)
    result = command.handler(state, argument)
    if command.name == "reset" or previous != (state.root, state.conversation_id):
        await state.reset_child_runs()
    reader.mode = state.approval
    reader.vim_mode = bool(getattr(state.config.runtime, "vim_mode", False))
    _sync_status_bar(reader, state)
    if result:
        console.print(f"[{theme.DIM}]{result}[/{theme.DIM}]")
    for line in await hook_events.flush(state):
        console.print(f"[{theme.WARN}]{escape(line)}[/{theme.WARN}]")
    # `level`/`development` model değiştirir: durum satırındaki model adı bayatlamasın.
    if command.name in {
        "agent",
        "fusion",
        "auto",
        "edits",
        "plan",
        "security",
        "bypass",
        "type",
        "mode",
        "level",
        "development",
    }:
        _print_status(console, state)


# --------------------------------------------------------------------------- #
# Tur çalıştırma
# --------------------------------------------------------------------------- #


def apply_auto_profile(line: str, state: ReplState, console: Console) -> None:
    """`/mode auto` açıksa görevi sınıflandırıp kademeyi bu tur için seç.

    Karar açıklanabilir olsun diye gerekçe basılır (master prompt §7.2). Profilin
    kademe karşılığı yoksa SESSİZCE geçilir: kullanıcının mevcut modeli korunur,
    tur auto yüzünden engellenmez.
    """
    if not state.auto_profile:
        return
    # Hafif ve saf; engines/agent __init__ zincirini import anında çekmemek için tembel.
    from ...engines.agent.auto_profile import auto_profile

    secim = auto_profile(line)
    tier_name = profile.resolve_tier_name(state.config, secim.profile)
    if tier_name is None:
        return
    state.config = model_select.apply_tier(state.config, tier_name)
    mesaj = messages.MODE_AUTO_SELECTED.format(profile=tier_name, reason=secim.reason)
    console.print(f"[{theme.DIM}]{mesaj}[/{theme.DIM}]")


async def _run_turn(
    line: str,
    state: ReplState,
    console: Console,
    background: BackgroundTasks,
    *,
    mode: Mode = Mode.NONE,
) -> bool:
    """Bir mesajı aktif motora gönder. Ctrl-C turu keser, REPL'den çıkmaz.

    Tur tamamlandıysa True, kullanıcı kestiyse False (hedef değerlendirmesi atlanır).
    """
    apply_auto_profile(line, state, console)
    task = asyncio.ensure_future(_dispatch(line, state, console, background, mode))
    completed = True
    moved: list[bool] = []

    def background_key() -> None:
        # Ctrl+B (#12): TUI ile aynı kural; bekleyen alt ajan yoksa tur arka plana taşınır.
        if background_key_action(state) is BackgroundKey.TURN and not task.done():
            moved.append(True)
            task.cancel()

    with _cancel_on_interrupt(task), session_keys(state).watching(background_key):
        try:
            await task
        except asyncio.CancelledError:
            completed = False
            if moved:
                note = interrupted_to_background(state, line)
                console.print(f"[{theme.DIM}]{escape(note)}[/{theme.DIM}]")
            else:
                console.print(f"[{theme.WARN}]{messages.REPL_TURN_CANCELLED}[/{theme.WARN}]")
    console.print()
    return completed


async def _continue_goal(state: ReplState, console: Console, background: BackgroundTasks) -> None:
    """`/goal` etkinse turu değerlendir ve gerekiyorsa hedef kipinde sürdür (P-058)."""
    if state.goal is None or not state.goal.is_active:
        return

    async def judge(
        condition: str,
        history: Sequence[Message],
        config: Config,
        publisher: EventPublisher | None,
    ) -> GoalJudgement:
        console.print(f"[{theme.DIM}]{messages.GOAL_JUDGING}[/{theme.DIM}]")
        task = asyncio.ensure_future(judge_goal(condition, history, config, publisher))
        with _cancel_on_interrupt(task):
            try:
                return await task
            except asyncio.CancelledError:
                return GoalJudgement(GoalVerdict.UNKNOWN, messages.REPL_TURN_CANCELLED)

    async def run(prompt: str) -> bool:
        return await _run_turn(prompt, state, console, background, mode=Mode.GOAL)

    def say(text: str) -> None:
        console.print(f"[{theme.ACCENT}]{escape(text)}[/{theme.ACCENT}]", highlight=False)

    sinks = (state.cost, *((state.usage_log,) if state.usage_log else ()))
    await goal_flow.drive_goal(
        state, run, say, judge=judge, publisher=goal_flow.SinkPublisher(sinks)
    )


async def _dispatch(
    line: str,
    state: ReplState,
    console: Console,
    background: BackgroundTasks,
    mode: Mode = Mode.NONE,
) -> None:
    if state.take_turn_engine() is Engine.FUSION:
        await _fusion_turn(line, state, console)
    else:
        await _agent_turn(line, state, console, background, mode)


async def _drive_agent(
    run_agent: Callable[..., Awaitable[AgentOutcome]],
    line: str,
    deps: AgentDeps,
    state: ReplState,
    console: Console,
    *,
    plan_mode: bool,
    extra_system: str,
    system_prompt: str | None = None,
    step_limit: int | None,
    workflow: bool = False,
    allowed_tools: set[str] | None = None,
    denied_tools: frozenset[str] = frozenset(),
) -> AgentOutcome:
    """Agent turunu çalıştır; MCP sunucuları tanımlıysa dış araçları da bağla.

    MCP kurulu değilse ya da bir sunucu başlatılamazsa DIŞ araçlar olmadan devam edilir
    (uyarı verilir): MCP bir zenginleştirmedir, turu engellememeli.
    """
    kwargs = {
        "history": state.history,
        "plan_mode": plan_mode,
        "extra_system": extra_system,
        "system_prompt": system_prompt,
        "step_limit": step_limit,
        "workflow": workflow,
        # Oturum kişiliğinin araç kısıtı (P-053); None = tam set. `denied_tools` yalnız
        # `disallowedTools` yazan kişilikte dolu.
        "allowed_tools": allowed_tools,
        "denied_tools": denied_tools,
    }
    if not state.config.mcp_servers and not state.config.hosted_connectors:
        return await run_agent(line, deps, **kwargs)
    try:
        from ...mcp_bridge.pool import ensure_hosted_tools, ensure_mcp_tools
    except ImportError:
        console.print(f"[{theme.WARN}]{messages.MCP_MISSING_DEP}[/{theme.WARN}]")
        return await run_agent(line, deps, **kwargs)
    # AgentDeps.__post_init__ None değerini yapılandırılmış defterle tamamlar.
    registry = cast("ToolRegistry", deps.base_registry)
    added: tuple[str, ...] = ()
    if state.config.mcp_servers:
        try:
            # Havuz açık bağlantıyı yeniden kullanır; her tur stdio sunucusunu
            # yeniden başlatmak ölçülmüş bir maliyetti (bkz. `mcp_bridge/pool.py`).
            added += await ensure_mcp_tools(
                state.config.mcp_servers,
                registry,
                retry_delays_s=state.config.runtime.retry_delays_s,
                root=getattr(deps.tool_context, "root", None),
            )
        except Exception as error:
            console.print(
                f"[{theme.WARN}]{messages.MCP_CONNECT_FAILED.format(error=error)}[/{theme.WARN}]"
            )
        # Döngü değişkeni görev satırını (`line`) EZMEZ: ilk bağlantı hatasında ajan uyarı
        # metniyle koşuyordu (ölçüldü 31 Ekim).
        for notice in new_failure_lines(state.config.mcp_servers):
            console.print(f"[{theme.WARN}]{notice}[/{theme.WARN}]")
    if state.config.hosted_connectors:
        # Biri düşerse diğeri yine eklenir: iki taşıma birbirinin arızasını
        # devralmaz.
        try:
            added += await ensure_hosted_tools(
                state.config, registry, root=getattr(deps.tool_context, "root", None)
            )
        except Exception as error:
            console.print(
                f"[{theme.WARN}]{messages.MCP_CONNECT_FAILED.format(error=error)}[/{theme.WARN}]"
            )
    if added:
        console.print(
            f"[{theme.DIM}]{messages.MCP_TOOLS_LOADED.format(count=len(added))}[/{theme.DIM}]"
        )
    if state.config.mcp_servers:
        # `/mcp__sunucu__istem` ve `@sunucu:kaynak` bağlantıdan sonra çözülür (P-049).
        from ...engines.agent.loop import AgentOutcome as _Outcome
        from ...mcp_bridge.reference_service import expand_mcp_references

        expansion = await expand_mcp_references(line, state.config.mcp_servers)
        for note in (*expansion.notes, *expansion.warnings):
            console.print(f"[{theme.DIM}]{escape(note)}[/{theme.DIM}]")
        if expansion.error:
            console.print(f"[{theme.WARN}]{escape(expansion.error)}[/{theme.WARN}]")
            return _Outcome(final_text="", messages=list(state.history), ok=False)
        line = expansion.task
        if expansion.context:
            kwargs["extra_system"] = "\n\n".join(
                part for part in (extra_system, expansion.context) if part
            )
    return await run_agent(line, deps, **kwargs)


async def _fusion_turn(line: str, state: ReplState, console: Console) -> None:
    from ..session import run_task

    # Beceri ekleri bu motorda kullanılmaz; bekleyip sonraki agent turuna sızmasın.
    state.take_pending_extras()
    renderer = ConsoleRenderer(
        console, show_all_answers=state.show_all_answers, show_call_details=True, bell=state.bell
    )
    tracer = LangfuseTracer(task=line)
    try:
        result: FusionResult = await run_task(
            line,
            state.config,
            # Maliyet toplayıcı OTURUM boyunca yaşar: her tur aynı toplayıcıyı besler.
            sinks=(renderer, state.cost, tracer, *((state.usage_log,) if state.usage_log else ())),
            task_type=state.task_type,
            synthesis=state.synthesis,
            memory=state.memory,
            health=state.health,
        )
    finally:
        # İptal/hata halinde de canlı gösterge durmalı; yoksa "hazırlanıyor…" dönmeye devam eder.
        renderer.abort()
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
    from ...engines.agent.approval import build_policy, may_run_unasked_commands
    from ...engines.agent.loop import AgentDeps
    from ...engines.agent.team_fork import run_forked_turn
    from ...engines.agent.verification import build_verifier
    from ...memory.checkpoint_store import JsonCheckpointStore
    from ..session import agent_mcp_scope

    state.prepare_persona_config()
    line = state.take_persona_initial(line)
    renderer = ConsoleRenderer(console, show_thinking=state.show_thinking, bell=state.bell)
    tracer = LangfuseTracer(task=line)
    async with EventBus() as bus:
        bus.subscribe(renderer)
        bus.subscribe(state.cost)
        bus.subscribe(tracer)
        if state.usage_log is not None:
            bus.subscribe(state.usage_log)
        # Tur checkpoint'i: konuşmanın kopyası + bu turun değişiklik kümesi (`/rewind`).
        checkpoint = state.checkpoints.begin(line, state.history)
        tool_context = _turn_tool_context(state, checkpoint.changes)
        partial = PartialTurn()
        prompter = ConsolePrompter(
            console,
            tool_context,
            flush=bus.drain,
            # Soru/onay sırasında canlı "hazırlanıyor…" satırını duraklat; yoksa
            # spinner cevap istemini ezip kullanıcıyı yazamaz hâle getirir.
            # Satır içi REPL'de tur boyu tuş gözcüsü de durur: onay istemi kanonik kipte okunur.
            suspend=lambda: prompt_pause(renderer.suspended, state),
            # "Her zaman reddet" (`r`, P-007) ret listesine yazar ve oturumu günceller.
            denials=AppDenials(config_persist(lambda: state.config, _config_setter(state))),
        )
        transport = state.remotion_transport
        if transport is None and state.remotion_browser is not None:
            transport = browser_transport(state.remotion_browser)
        # `Notification` kancası onay sorusundan hemen önce (P-009).
        confirm_prompter = notifying(prompter, state.hooks())
        _register_elicitation(prompter)  # MCP sunucusu girdi isterse bu taraf sorar (#257)
        deps = AgentDeps(
            config=state.config,
            session_persona=state.persona,
            main_config_applied=state.main_config_applied,
            mcp_connector=agent_mcp_scope,
            child_runs=state.child_runs,
            interactive=True,
            publisher=bus,
            policy=build_policy(state.approval, confirm_prompter, state.approval_memory),
            approval_mode=lambda: state.approval,
            policy_for_mode=lambda wanted: build_policy(
                wanted, confirm_prompter, state.approval_memory
            ),
            tool_context=tool_context,
            asker=prompter,
            code_index=state.memory.code_index if state.memory.enabled else None,
            lessons=state.memory.lessons,
            capabilities=state.capabilities,
            plain_memory=state.plain_memory,
            home=state.home,
            allowed_commands=state.allowed_commands,
            permission_rules=state.permission_rules(),
            hooks=state.hooks(),
            auto_review=state.approval_memory.auto_review,
            background=background,
            verifier=build_verifier(
                state.config,
                root=state.root,
                tool_context=tool_context,
                remotion_state=tool_context.remotion_contract,
                remotion_transport=transport,
                dev_server_allowed=lambda: may_run_unasked_commands(state.approval),
            ),
            # `/type` agent turunda da etkili olmalı: görev tipi model seçimini
            # yönlendirir (`select_agent_spec`). Geçirilmediğinde "general"a düşülüyor
            # ve `task_model_map` REPL'de sessizce uygulanmıyordu.
            task_type=state.task_type,
            health=state.health,
            checkpoint_store=JsonCheckpointStore(
                state.config.memory_dir / "workflow-checkpoints",
                root=state.root,
                conversation_id=state.conversation_id,
            ),
            conversation_id=state.conversation_id,
            # İptal/hata halinde o turun araç sonuçları geçmişten düşmesin (L2-12).
            journal=partial,
        )
        # Değişiklik kümesi tur boyunca yerinde dolar; kesilen turdaki yarım
        # yazılmış dosyalar da `/undo` ile geri alınabilsin.
        state.last_changes = tool_context.changes
        digest = state.take_pending_digest()
        # Esc ile durdurma bu turun görevine bağlanır (P-033; `tools/desktop_turn`).
        desktop_turn.begin(tool_context)
        try:
            persona = launch_prompts_mod.apply_to_turn(persona_turn(state.persona), state)
            extras = state.take_pending_extras()
            # Önceki becerinin ön onayı kalkar; bu çağrınınki girer (#142, #180).
            skill_grants.begin_turn(tool_context, extras.grants)
            # Becerinin `model`/`effort` alanı yalnız bu turun yapılandırmasıdır (P-020).
            deps.config = extras.turn_config(deps.config)
            turn_extra_system = "\n\n".join(
                part
                for part in (
                    persona.extra_system,
                    macros.mode_prompt(mode),
                    digest,
                    extras.context,
                )
                if part
            )
            outcome = await _drive_agent(
                extras.fork_runner(run_forked_turn) if macros.mode_fork(mode) else run_agent,
                line,
                deps,
                state,
                console,
                plan_mode=state.approval.value == "plan",
                extra_system=turn_extra_system,
                system_prompt=persona.system_prompt,
                step_limit=macros.mode_step_limit(mode),
                workflow=macros.mode_workflow(mode),
                # Oturum kişiliğinin araç kısıtı (P-053) ile becerinin `allowed-tools`'u kesişir.
                allowed_tools=extras.merged_tools(persona.allowed_tools),
                denied_tools=extras.merged_denied(persona.denied_tools),
            )
            # Boş cevap yalnızca tur temiz bittiyse hatadır; bkz. `cli/session.py`.
            if not outcome.final_text.strip() and outcome.ok:
                bus.publish(ErrorOccurred(messages.AGENT_EMPTY_ANSWER))
            # Rozet yalnızca BAŞARILI turda anlamlıdır; bkz. `cli/session.py`.
            if outcome.ok and outcome.made_no_changes and state.approval.value != "plan":
                bus.publish(NoFileChanges())
            elif tool_context.changes.paths:
                bus.publish(FilesChanged(_changed_names(tool_context)))
            # Takip önerileri: yeni model çağrısı YOK, turun kendi kanıtından.
            oneriler = suggest_followups(
                evidence_from_turn(
                    outcome,
                    tool_context,
                    verification_command=next(iter(state.config.runtime.verification_commands), ""),
                )
            )
            if oneriler:
                bus.publish(
                    FollowupsSuggested(tuple((item.label, item.prompt) for item in oneriler))
                )
            bus.publish(TurnFinished())
            # Plan kipinde biten tur plan dosyasını YAZDIYSA (`plan_mode.record_plan`,
            # `outcome.plan_path`) kart komut döngüsünde, canlı gösterge kapandıktan sonra
            # açılır. Ölçüldü (31 Ekim): yol koşulsuz kuruluyordu; plan_files=false ya da
            # yazma hatasında kart olmayan/bayat dosyayı gösteriyordu.
            if outcome.plan_path is not None:
                state.pending_plan = outcome.plan_path
            print_rule_notices(console, state.approval_memory)
        except (asyncio.CancelledError, Exception):
            state.history = partial.history_after_interruption(
                previous=state.history, task=line, root=state.root
            )
            # Tüketilen `!`/`@` bağlamı ve künye iptalde kaybolmaz (tam ekranla aynı, L2-24).
            state.restore_pending_digest(digest)
            raise
        finally:
            # İptal/hata halinde TurnFinished yayınlanmaz; canlı gösterge yine de durmalı
            # ve iz verisi (Langfuse) kaybolmamalı (L2-26).
            renderer.abort()
            tracer.flush()
            # Masaüstü kilidi ve oturumu tur ile sınırlıdır (bkz. `tools/desktop_turn`).
            if desktop_turn.finish(tool_context):
                console.print(f"[{theme.WARN}]{messages.BILGISAYAR_ESC_STOPPED}[/{theme.WARN}]")
    state.history = outcome.messages
    # Turda açılan/okunan PR oturumun künyesi olur; durum satırında görünür (P-057).
    linked_pr.bind_from_turn(state, outcome.tool_uses)
    # `enter_worktree`/`exit_worktree` isteği tur bitince uygulanır (kök tur ortasında değişmez).
    switched = await state.apply_worktree_switch(tool_context.worktree_switch)
    if switched:
        console.print(f"[{theme.DIM}]{escape(switched)}[/{theme.DIM}]")


def _config_setter(state: ReplState) -> Callable[[Config], None]:
    """Turun dışında yazılan ayarı (ret listesi, P-007) oturuma işle."""

    def apply(updated: Config) -> None:
        state.config = updated

    return apply


def _turn_tool_context(state: ReplState, changes: ChangeSet | None = None) -> ToolContext:
    """Turun araç bağlamı; yapılandırma ayarları `run_agent_task` ile aynı yerden işlenir."""
    from ..session import apply_runtime_settings

    return apply_runtime_settings(
        ToolContext(
            root=state.root,
            extra_roots=state.extra_roots,
            restrict_to_root=state.config.runtime.restrict_to_root,
            block_reads_outside_root=state.config.runtime.block_reads_outside_root,
            block_writes_outside_root=state.config.runtime.block_writes_outside_root,
            remotion_browser=state.remotion_browser,
            browser=browser_command.turn_browser(state),
            local_origins=browser_command.turn_origins(state),
            changes=changes if changes is not None else ChangeSet(),
            cron=state.cron,
            chrome=chrome_cli.bridge_of(state.chrome),
        ),
        state.config,
    )


def _changed_names(tool_context: ToolContext) -> tuple[str, ...]:
    """Değişen yolları köke göreli ver; bkz. `cli/session.py`."""
    from ...tools.files import display_path

    return tuple(display_path(tool_context, path) for path in tool_context.changes.paths)


async def compact_history(state: ReplState) -> str:
    """`/compact`: uzun geçmişi özetleyerek kısalt."""
    before = len(state.history)
    gate = await state.hooks().pre_compact("manual")
    if gate.blocked:
        # Claude: PreCompact çıkış 2 / `decision: block` özetlemeyi engeller.
        return messages.HOOKS_COMPACT_BLOCKED.format(reason=gate.reason)
    previous = list(state.history)
    state.history = await compress(state.history, config=state.config)
    after = len(state.history)
    if after >= before:
        return messages.REPL_NOTHING_TO_COMPACT
    summary = "\n\n".join(m.content for m in state.history if m not in previous)
    await state.hooks().post_compact("manual", summary)
    # SessionStart(compact): kancanın bağlamı sonraki tura eklenir (P-009).
    verdict = await state.hooks().compacted()
    # InstructionsLoaded (#169): sonraki turda talimatlar `compact` nedeniyle yeniden bildirilir.
    from ...engines.agent import instructions_hook

    instructions_hook.mark_compacted(state.hooks())
    if verdict.context_text:
        prefixes.push_pending_context(
            state, context_reminder(HookEvent.SESSION_START, verdict.context_text)
        )
    summary = messages.REPL_COMPACTED.format(before=before, after=after)
    return "\n".join((summary, *hook_events.verdict_lines(verdict)))


# --------------------------------------------------------------------------- #
# Kapanış ve kesme
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _cancel_on_interrupt(task: asyncio.Future[ResultT]) -> Iterator[None]:
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


def _sync_status_bar(
    reader: ReplInput, state: ReplState, background: BackgroundTasks | None = None
) -> None:
    """Durum çubuğundaki bağlamı güncel tut (motor, görev tipi, model, arka plan işleri).

    Arka plan sayacı (Faz 5, Görev 2): CANLI ilerleme hâlâ basılmaz (bilinçli
    tasarım, `ui/renderer.py`'deki `if not event.background` ile aynı ruh) —
    yalnız `BackgroundTasks.pending` zaten hesapladığı TOPLU sayı gösterilir,
    yeni bir sayaç İCAT EDİLMEDİ. `background=None` (ör. slash komutlarından
    sonra) verilirse sessizce eklenmez, hata VERMEZ.
    """
    from .status_view import context_label

    parts = [state.engine.value, state.task_type, state.config.agent.model]
    # Bağlam sayacı (P-027): geçmiş doluysa eşiğe göre yüzde ve tahmini token.
    if baglam := context_label(state):
        parts.append(baglam)
    if background is not None and background.pending:
        parts.append(f"{background.pending} arka plan işi")
    if state.linked_pr is not None:
        parts.append(state.linked_pr.label)
    reader.context = " · ".join(parts)


def session_info(state: ReplState) -> banner.SessionInfo:
    """Karşılama kutusunda gösterilecek oturum bilgilerini topla."""
    from ... import __version__

    return banner.SessionInfo(
        version=__version__,
        engine=state.engine.value,
        approval=state.approval.value,
        model=state.config.agent.model,
        working_dir=_short_path(state.root),
        lesson_count=state.memory.lessons.count() if state.memory.enabled else None,
        agent=state.persona.name if state.persona is not None else "",
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


def _register_elicitation(asker: object) -> None:
    try:
        from ...mcp_bridge.elicitation import register_elicitation_asker
    except ImportError:  # `mcp` paketi kurulu değil
        return
    register_elicitation_asker(asker)  # type: ignore[arg-type]

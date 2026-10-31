"""Oturum kurulumu — veriyolu, dinleyiciler ve sağlayıcı burada birleştirilir.

Tek bir görevi çalıştırmanın uçtan uca akışı budur. Faz 2'den itibaren burada
motorlar (fusion, agent) çağrılacak; kurulum akışı aynı kalacak.

Dikkat: bu dosya hiçbir şey BASMAZ. Kullanıcıya ne gösterileceğine dinleyiciler
karar verir; buradan yalnızca olay yayınlanır.
"""

from __future__ import annotations

import hashlib
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ..config.browser_profiles import browser_session_from
from ..config.models import Config, mcp_secret_env_names
from ..config.permission_rules import load_permission_rules
from ..config.permissions import load_allowed_commands
from ..config.sandbox_config import fusion_secret_paths, sandbox_policy
from ..core.artifacts import ArtifactStore
from ..core.browser_session import BrowserSession
from ..core.changeset import ChangeSet
from ..core.concurrency import BackgroundTasks
from ..core.events import (
    DesktopEscapeStopped,
    ErrorOccurred,
    EventSink,
    FilesChanged,
    FollowupsSuggested,
    FusionCompleted,
    NoFileChanges,
    StatusChanged,
    TurnFinished,
    TurnOutcome,
)
from ..core.followups import suggest_followups
from ..core.health import HealthRegistry
from ..core.protocols import TurnJournal
from ..core.remotion_browser import RemotionBrowser
from ..core.session_cron import SessionCron
from ..core.skill_context import SkillSelection
from ..core.steering import SteeringQueue
from ..core.tools import ChromeControl, ToolContext
from ..core.turn_deadline import TurnDeadline
from ..core.types import (
    CompletionRequest,
    FusionResult,
    Message,
    VerdictSource,
    is_rate_limit_error,
)
from ..core.worktree import WorktreeSwitch
from ..engines.agent import AgentOutcome, run_agent
from ..engines.agent.approval import (
    ApprovalMemory,
    ApprovalMode,
    ApprovalPolicy,
    build_policy,
    may_run_unasked_commands,
)
from ..engines.agent.child_runs import ChildRuns
from ..engines.agent.loop import AgentDeps
from ..engines.agent.remotion_bridge import FrameTransport
from ..engines.agent.tool_filter import DeniedToolsPolicy
from ..engines.agent.turn_evidence import evidence_from_turn
from ..engines.agent.verification import build_verifier
from ..engines.fusion import run_fusion
from ..engines.retention import purge_local_state_daily
from ..memory.checkpoint_store import JsonCheckpointStore
from ..memory.factory import Memory, build_memory, null_memory
from ..memory.plain_memory import PlainMemory, build_plain_memory
from ..observability.audit import AuditSink
from ..observability.bus import EventBus
from ..observability.cost import CostTracker
from ..observability.json_sink import JsonRenderer
from ..observability.trace_store import TraceStore, TraceWriter
from ..observability.tracing import LangfuseTracer
from ..providers.health_setup import build_health
from ..tools import desktop_turn
from ..tools.capabilities import CapabilityRegistry
from ..tools.capability_overrides import registry_from_config
from ..tools.remotion_observe import browser_transport
from ..ui import messages
from .mcp_notice import new_failure_lines

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi için
    from ..engines.agent.approval import Prompter
    from ..engines.agent.engine_tools import UserAsker

    class AgentPrompter(Prompter, UserAsker, Protocol):
        """Hem onay soran hem soru sorabilen arayüz (terminal uygulaması ikisini de yapar)."""

    #: Veriyolu boşaltma fonksiyonunu alıp prompter üreten fabrika.
    PrompterFactory = Callable[[Callable[[], Awaitable[None]]], AgentPrompter]


def build_request(task: str, config: Config) -> CompletionRequest:
    """Görev metnini yapılandırmadaki çalışma zamanı ayarlarıyla isteğe çevir."""
    runtime = config.runtime
    return CompletionRequest(
        messages=(Message("user", task),),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
    )


async def run_task(
    task: str,
    config: Config,
    *,
    sinks: tuple[EventSink, ...],
    task_type: str = "general",
    synthesis: bool | None = None,
    memory: Memory | None = None,
    health: HealthRegistry | None = None,
) -> FusionResult:
    """Görevi fusion motoruyla çalıştır ve sonucu döndür.

    Hata fırlatmaz: hiçbir aday yanıt veremezse `VerdictSource.NONE` ile döner ve
    kullanıcıya gösterilecek açıklama olay olarak yayınlanır.
    """
    started_at = time.monotonic()
    async with EventBus() as bus:
        for sink in sinks:
            bus.subscribe(sink)

        store = memory or null_memory()
        _warn_if_unavailable(store, bus)
        result = await run_fusion(
            task,
            config,
            publisher=bus,
            task_type=task_type,
            synthesis=synthesis,
            memory=store.performance,
            health=health,
        )
        if result.source is VerdictSource.NONE:
            bus.publish(ErrorOccurred(_failure_message(result), fatal=True))
        else:
            bus.publish(FusionCompleted(result))
        bus.publish(
            TurnOutcome(
                status="failed" if result.source is VerdictSource.NONE else "completed",
                elapsed_s=time.monotonic() - started_at,
            )
        )
        bus.publish(TurnFinished())
        return result


def _failure_message(result: FusionResult) -> str:
    """Tüm adaylar başarısızsa: hız sınırı mı, genel bir sorun mu?"""
    if any(candidate.is_rate_limited for candidate in result.candidates):
        return messages.ERROR_RATE_LIMITED
    return messages.ERROR_NO_ANSWER


def apply_runtime_settings(tool_context: ToolContext, config: Config) -> ToolContext:
    """Yapılandırmadaki araç ayarlarını bağlama işle (tek yer; her tur yolu bunu çağırır).

    Ölçüldü (31 Ekim): REPL kendi `ToolContext`'ini kurup `run_agent`'a doğrudan veriyordu;
    `runtime.desktop_screenshot_max_width`, `desktop_exclude_fusion_window` ve daha önce
    `shell_sandbox`/`edit_fuzzy_match`/`shell_workspace_fingerprint` orada sessizce varsayılanda
    kalıyordu. TUI ve `fusion run` `run_agent_task` üzerinden geçtiği için etkilenmiyordu.
    """
    return replace(
        tool_context,
        # MCP sırları ortamda yaşar; araç çocuk süreçleri (run_shell) onları miras almaz.
        hidden_env=tool_context.hidden_env | mcp_secret_env_names(config.mcp_servers),
        # run_shell işletim sistemi sandbox'ı yapılandırmadan gelir (Q1-16).
        shell_sandbox=config.runtime.shell_sandbox,
        # Okuma engeli, ağ allowlist'i, ek yazma kökleri (P-010); Fusion sırları her zaman engelli.
        sandbox_policy=sandbox_policy(
            config.sandbox,
            home=Path.home(),
            root=tool_context.root,
            extra_deny=fusion_secret_paths(),
        ),
        edit_fuzzy_match=config.runtime.edit_fuzzy_match,
        post_edit_syntax_check=config.runtime.post_edit_syntax_check,
        shell_fingerprint=config.runtime.shell_workspace_fingerprint,
        desktop_screenshot_max_width=config.runtime.desktop_screenshot_max_width,
        desktop_exclude_fusion_window=config.runtime.desktop_exclude_fusion_window,
        desktop_settings=getattr(config, "desktop", tool_context.desktop_settings),
    )


async def run_agent_task(
    task: str,
    config: Config,
    *,
    sinks: tuple[EventSink, ...],
    prompter_factory: PrompterFactory,
    mode: ApprovalMode = ApprovalMode.AUTO,
    task_type: str = "general",
    root: Path | None = None,
    home: Path | None = None,
    extra_system: str = "",
    interactive: bool | None = None,
    memory: Memory | None = None,
    extra_roots: tuple[Path, ...] = (),
    history: list[Message] | None = None,
    background: BackgroundTasks | None = None,
    tool_context: ToolContext | None = None,
    changes: ChangeSet | None = None,
    chrome_bridge: ChromeControl | None = None,
    capabilities: CapabilityRegistry | None = None,
    plain_memory: PlainMemory | None = None,
    system_prompt: str | None = None,
    images: tuple[str, ...] = (),
    conversation_id: str = "cli",
    step_limit: int | None = None,
    approval_memory: ApprovalMemory | None = None,
    steering: SteeringQueue | None = None,
    child_runs: ChildRuns | None = None,
    selected_skill: SkillSelection | None = None,
    current_approval: Callable[[], ApprovalMode] | None = None,
    chat_mode: bool = False,
    workflow: bool = False,
    allowed_tools: set[str] | None = None,
    denied_tools: frozenset[str] = frozenset(),
    health: HealthRegistry | None = None,
    journal: TurnJournal | None = None,
    require_remotion_kit: bool = False,
    remotion_transport: FrameTransport | None = None,
    remotion_browser: RemotionBrowser | None = None,
    deadline: TurnDeadline | None = None,
    turn_runner: Callable[..., Awaitable[AgentOutcome]] | None = None,
    cron: SessionCron | None = None,
    strict_tool_names: bool = False,
    worktree_switch: WorktreeSwitch | None = None,
    browser: BrowserSession | None = None,
) -> AgentOutcome:
    """Görevi agent motoruyla (araçlar + onay + öz-denetim) çalıştır.

    `turn_runner` verilirse `run_agent` yerine o koşar (aynı imza): `/subtask` turu fork alt
    ajanda yürüten `team_fork.run_forked_turn` böyle takılır (P-054).

    `denied_tools` (headless `--disallowed-tools`, oturum kişiliğinin `disallowedTools`u;
    P-026/P-053) adı geçen araçları modelin kümesinden çıkarır ve sormadan engelleyen bir
    sarmalayıcıyı seçili onay politikasının üstüne koyar.

    `strict_tool_names` (headless) izin/yasak listesinde bu oturumda bulunmayan bir ad
    varsa modeli hiç çağırmadan başarısız döner: yazım hatası sessizce araçsız tur ya da
    kapanmamış bir yasak demekti (31 Ekim).

    `workflow` kullanıcının bu tur için plan motorunu seçtiğini söyler (`/plan-yurut`).

    `interactive` False ise `ask_user` aracı modele HİÇ sunulmaz: cevaplanamayacak
    soru sormak turu boşa harcar. `history` verilirse çok-turlu sohbet sürdürülür.

    `browser` (P-045) paylaşılan tarayıcıdır (masaüstü Tarayıcı paneli): verilirse tur onu
    kullanır, yerel izin kümesi onunkidir ve tur sonunda kapatılmaz (`persistent`).

    `background` verilirse ders çıkarımı gibi tur SONRASI işler fire-and-forget çalışır
    ve cevabı bekletmez; verilmezse bu işler turu bloklar (gözlemlenen "ekstra gecikme").
    """
    can_ask = sys.stdin.isatty() if interactive is None else interactive
    started_at = time.monotonic()

    async with EventBus() as bus:
        for sink in sinks:
            bus.subscribe(sink)
        # Her araç sonucu kalıcı denetim günlüğüne de yazılır (silinmez).
        # Denetim kökü ARAÇ kökü ile aynı olmalı: çağıran `tool_context` verdiyse gerçek
        # kök odur, `root` değil (göreli yol raporu kayıyordu; L1-31).
        audit_root = tool_context.root if tool_context is not None else (root or Path.cwd())
        bus.subscribe(AuditSink(config.memory_dir / "audit", conversation_id, root=audit_root))
        # 30 günden eski iz/artifact/tamamlanmış checkpoint (günde en çok bir kez; L1-30, M1-44).
        purge_local_state_daily(config.memory_dir, now=time.time())

        # Prompter veriyolunu tanır: terminali devralmadan önce bekleyen olayları
        # boşaltır, böylece onay paneli akan çıktının ortasına düşmez.
        prompter = prompter_factory(bus.drain)
        store = memory or null_memory()
        _warn_if_unavailable(store, bus)
        # Çağıran bir bağlam verdiyse O kullanılır. `/undo` turun değişiklik
        # kümesine erişebilmek zorundadır; bağlam burada gizlice kurulduğunda
        # çağıranın elinde hiçbir referans kalmıyor ve geri alma sessizce
        # işlevsiz kalıyordu (ölçüldü: TUI'de `/undo` her zaman "geri alınacak
        # değişiklik yok" diyordu, oysa dosyalar değişmişti).
        tool_context = tool_context or ToolContext(
            root=root or Path.cwd(),
            chrome=chrome_bridge,
            extra_roots=extra_roots,
            restrict_to_root=config.runtime.restrict_to_root,
            browser=browser or browser_session_from(config),
            local_origins=(
                browser.origins if browser is not None and browser.origins is not None else set()
            ),
            block_reads_outside_root=config.runtime.block_reads_outside_root,
            block_writes_outside_root=config.runtime.block_writes_outside_root,
            # Bağlamı şişiren araç çıktısı kırpılmak yerine diske alınır: bilgi
            # kaybolmaz, model gerektiğinde dosyayı açar (context rot).
            artifacts=ArtifactStore(config.memory_dir / "artifacts" / _artifact_id()),
        )
        tool_context = apply_runtime_settings(tool_context, config)
        if cron is not None:
            # Oturum zamanlayıcısı (masaüstü): `cron_*` araçları sohbetin listesine yazar.
            tool_context = replace(tool_context, cron=cron)
        if changes is not None:
            # Çağıran (masaüstü oturumu) turun ilk-hâl anlık görüntülerini geri alma
            # günlüğüne aktarabilsin diye kümeyi kendisi verir.
            tool_context = replace(tool_context, changes=changes)
        if worktree_switch is not None:
            # `enter_worktree`/`exit_worktree` isteği tur bitince çağıranda (masaüstü, tek
            # atış) okunur; verilmezse istek bağlamın kendi anahtarında kalır ve kaybolur.
            tool_context = replace(tool_context, worktree_switch=worktree_switch)
        if conversation_id:
            tool_context = replace(
                tool_context,
                job_scope=hashlib.sha256(
                    f"{config.memory_dir.resolve()}\0{conversation_id}".encode()
                ).hexdigest(),
            )
        if remotion_browser is not None:
            tool_context = replace(tool_context, remotion_browser=remotion_browser)
        if remotion_transport is None and tool_context.remotion_browser is not None:
            remotion_transport = browser_transport(tool_context.remotion_browser)
        if require_remotion_kit:
            tool_context.remotion_contract.require()

        def _policy(active_mode: ApprovalMode) -> ApprovalPolicy:
            policy: ApprovalPolicy = build_policy(active_mode, prompter, approval_memory)
            return DeniedToolsPolicy(policy, denied_tools) if denied_tools else policy

        deps = AgentDeps(
            config=config,
            deadline=deadline,
            publisher=bus,
            # Sohbet boyunca yaşayan çağıran kendi hafızasını verir; yoksa
            # "oturum boyunca" izni bu turla birlikte biter (`fusion run`).
            policy=_policy(mode),
            denied_tools=frozenset(denied_tools),
            steering=steering,
            child_runs=child_runs if child_runs is not None else ChildRuns(),
            selected_skill=selected_skill,
            policy_factory=(lambda: _policy(current_approval())) if current_approval else None,
            # Alt ajan kipi (P-034) üst kipten SIKILAŞTIRILIR; aynı yasak sarmalayıcısıyla kurulur.
            approval_mode=current_approval or (lambda: mode),
            policy_for_mode=_policy,
            approval_revision=(
                lambda: (current_approval(), approval_memory.revision if approval_memory else 0)
            )
            if current_approval
            else None,
            tool_context=tool_context,
            asker=prompter if can_ask else None,
            code_index=store.code_index if store.enabled else None,
            lessons=store.lessons,
            capabilities=capabilities
            or (
                registry_from_config(
                    config, home, tool_context.root, extra_roots=tool_context.extra_roots
                )
                if home is not None
                else None
            ),
            # Düz metin bellek (P-036): çağıran vermezse yapılandırmaya göre projeninki.
            # `--no-memory` (boş depo) belleği de kapatır: kullanıcı "yazma" demiştir.
            plain_memory=plain_memory
            if plain_memory is not None
            else (build_plain_memory(config, tool_context.root) if store.enabled else None),
            home=home,
            allowed_commands=load_allowed_commands(tool_context.root),
            permission_rules=load_permission_rules(
                tool_context.root,
                block_reads_outside_root=config.runtime.block_reads_outside_root,
                block_writes_outside_root=config.runtime.block_writes_outside_root,
            ),
            # Otomatik kip denetçisi (P-011): sayaçlar oturum hafızasıyla yaşar.
            auto_review=approval_memory.auto_review if approval_memory is not None else None,
            verifier=build_verifier(
                config,
                root=tool_context.root,
                tool_context=tool_context,
                remotion_state=tool_context.remotion_contract,
                remotion_transport=remotion_transport,
                dev_server_allowed=lambda: may_run_unasked_commands(
                    current_approval() if current_approval else mode
                ),
            ),
            task_type=task_type,
            background=background,
            checkpoint_store=JsonCheckpointStore(
                config.memory_dir / "workflow-checkpoints",
                root=tool_context.root,
                conversation_id=conversation_id,
            ),
            conversation_id=conversation_id,
            # Kayıt verilmezse tur kendi kaydını kurar: circuit breaker ve ortak hız
            # defteri tek atışlık `fusion agent`ta da çalışmalı (eskiden hiç yoktu).
            health=health or build_health(config),
            journal=journal,
        )
        # Masaüstü oturumu turun görevine bağlanır: Esc iptali bu görevi keser (P-033).
        desktop_turn.begin(tool_context)
        try:
            outcome = await _run_agent_with_mcp(
                task,
                deps,
                config,
                bus,
                history=history,
                mode=mode,
                extra_system=extra_system,
                system_prompt=system_prompt,
                images=images,
                step_limit=step_limit,
                chat_mode=chat_mode,
                workflow=workflow,
                allowed_tools=allowed_tools,
                denied_tools=denied_tools,
                turn_runner=turn_runner,
                strict_tool_names=strict_tool_names,
            )
        finally:
            # Masaüstü kilidi TUR ile sınırlıdır: iptal ya da hatada da bırakılır; yoksa başka
            # sohbet 300 sn "o tur bitince yeniden dene" alır (bkz. `tools/desktop_lock`).
            # Esc dinleyicisi kapanır, gizlenen uygulamalar geri gelir (P-033).
            if desktop_turn.finish(tool_context):
                bus.publish(DesktopEscapeStopped())

        # Boş cevap YALNIZCA tur temiz bittiyse hatadır. Bütçe dolduğunda ya da
        # kapı turu kestiğinde sebep ZATEN yayınlandı; ikinci bir "(model boş yanıt
        # verdi)" satırı basmak, açıklanmış bir durumu ikinci kez ve daha az
        # bilgiyle söylemekti.
        if not outcome.final_text.strip() and outcome.ok:
            bus.publish(ErrorOccurred(messages.AGENT_EMPTY_ANSWER, fatal=True))
        elif not outcome.ok and is_rate_limit_error(outcome.final_text):
            bus.publish(ErrorOccurred(messages.ERROR_RATE_LIMITED, fatal=False))
        elif not outcome.ok and not outcome.budget_stopped:
            # Bütçe durdurmasında sebep zaten yayınlandı; cevabı ikinci kez ve
            # hata kılığında basmak kendiyle çelişen satır üretir.
            bus.publish(ErrorOccurred(outcome.final_text, fatal=False))
        # Rozet yalnızca BAŞARILI turda anlamlıdır. Başarısız turda hata mesajı
        # zaten "değişiklik yapılmış kabul edilmemelidir" diyor; rozeti de basmak
        # aynı olguyu iki kez, iki farklı üslupla söylemekti ve kullanıcı ikincisini
        # yeni bilgi sanıyordu. Plan modunda değişiklik zaten yasaktır.
        if outcome.ok and outcome.made_no_changes and mode is not ApprovalMode.PLAN:
            bus.publish(NoFileChanges())
        elif tool_context.changes.paths:
            # Liste modelin hafızasından değil değişiklik kümesinden gelir.
            bus.publish(FilesChanged(_changed_names(tool_context)))
        if outcome.ok:
            status = "completed"
        else:
            status = "partial" if tool_context.changes.paths else "failed"
        # Takip önerileri: YENİ MODEL ÇAĞRISI YOK, turun kendi kanıtından.
        # Kanıt yoksa olay hiç yayınlanmaz (bkz. `core/followups.py`).
        oneriler = suggest_followups(
            evidence_from_turn(
                outcome,
                tool_context,
                verification_command=next(iter(config.runtime.verification_commands), ""),
            )
        )
        if oneriler:
            bus.publish(FollowupsSuggested(tuple((item.label, item.prompt) for item in oneriler)))
        bus.publish(TurnOutcome(status=status, elapsed_s=time.monotonic() - started_at))
        bus.publish(TurnFinished())
        return outcome


async def _run_agent_with_mcp(
    task: str,
    deps: AgentDeps,
    config: Config,
    bus: EventBus,
    *,
    history: list[Message] | None,
    mode: ApprovalMode,
    extra_system: str,
    system_prompt: str | None = None,
    images: tuple[str, ...] = (),
    step_limit: int | None = None,
    chat_mode: bool = False,
    workflow: bool = False,
    allowed_tools: set[str] | None = None,
    denied_tools: frozenset[str] = frozenset(),
    turn_runner: Callable[..., Awaitable[AgentOutcome]] | None = None,
    strict_tool_names: bool = False,
) -> AgentOutcome:
    """`run_agent` çağır; yapılandırılmış dış MCP sunucuları varsa önce bağla.

    `fusion agent`/tek-atış CLI yolu MCP'siz çalışıyordu — yalnızca REPL
    (`cli/repl/loop.py`) dış araçları bağlıyordu. Kullanıcı "şu MCP'yi kur"
    dedikten sonra `fusion agent` ile de bir görev verirse (ör. otomasyon
    betiği) bağlı MCP'nin araçları modele hiç sunulmuyordu. MCP bir
    zenginleştirmedir; kurulu değilse ya da bağlanamazsa tur YİNE DE
    MCP'siz devam eder (REPL ile aynı davranış).
    """
    plan_mode = mode is ApprovalMode.PLAN
    runner = turn_runner or run_agent

    async def _run() -> AgentOutcome:
        if strict_tool_names:
            # MCP araçları bağlandıktan SONRA denetlenir: `<sunucu>__<araç>` adları ancak
            # o zaman defterdedir.
            rejected = _reject_unknown_tools(deps, allowed_tools, bus)
            if rejected is not None:
                return rejected
        return await runner(
            task,
            deps,
            history=history,
            plan_mode=plan_mode,
            chat_mode=chat_mode,
            allowed_tools=allowed_tools,
            denied_tools=denied_tools,
            extra_system=extra_system,
            system_prompt=system_prompt,
            images=images,
            step_limit=step_limit,
            workflow=workflow,
        )

    if not config.mcp_servers and not config.hosted_connectors:
        return await _run()
    try:
        from ..mcp_bridge.pool import ensure_hosted_tools, ensure_mcp_tools
    except ImportError:
        bus.publish(ErrorOccurred(messages.MCP_MISSING_DEP, fatal=False))
        return await _run()
    eklenen: tuple[str, ...] = ()
    if config.mcp_servers:
        try:
            # Bağlantı TURUN değil oturumun kaynağıdır: havuz açık bağlantıyı
            # yeniden kullanır (bkz. `mcp_bridge/pool.py`). Kapatma oturum
            # kapanışında yapılır, tur içinde değil.
            eklenen += await ensure_mcp_tools(
                config.mcp_servers, deps.base_registry, retry_delays_s=config.runtime.retry_delays_s
            )
        except Exception as error:
            bus.publish(ErrorOccurred(messages.MCP_CONNECT_FAILED.format(error=error), fatal=False))
        for line in new_failure_lines(config.mcp_servers):
            bus.publish(ErrorOccurred(line, fatal=False))
    if config.hosted_connectors:
        # Sağlayıcı-barındırmalı connector'lar ayrı yoldan gelir: bağlantı yoktur,
        # araçlar sağlayıcının oturumunda yaşar. Biri düşerse diğeri yine eklenir.
        try:
            eklenen += await ensure_hosted_tools(config, deps.base_registry)
        except Exception as error:
            bus.publish(ErrorOccurred(messages.MCP_CONNECT_FAILED.format(error=error), fatal=False))
    # Yapı denetimi hangi araçların VAR olduğunu bilmeli: bir biçimi zaten doğru
    # üreten araç varsa model elle yazmaya değil ona yönlendirilir.
    deps.tool_context.available_tools.update(eklenen)
    if config.mcp_servers:
        # `/mcp__sunucu__istem` ve `@sunucu:kaynak` bağlantı kurulduktan sonra çözülür (P-049).
        from ..mcp_bridge.reference_service import expand_mcp_references

        expansion = await expand_mcp_references(task, config.mcp_servers)
        for note in expansion.notes:
            bus.publish(StatusChanged(note))
        for warning in expansion.warnings:
            bus.publish(ErrorOccurred(warning, fatal=False))
        if expansion.error:
            bus.publish(ErrorOccurred(expansion.error, fatal=True))
            return AgentOutcome(final_text=expansion.error, messages=list(history or []), ok=False)
        task = expansion.task
        if expansion.context:
            extra_system = "\n\n".join(part for part in (extra_system, expansion.context) if part)
    return await _run()


def _reject_unknown_tools(
    deps: AgentDeps, allowed_tools: set[str] | None, bus: EventBus
) -> AgentOutcome | None:
    """İzin/yasak listesinde defterde olmayan ad varsa başarısız sonuç; yoksa None."""
    from ..engines.agent.engine_tools import build_agent_registry
    from ..engines.agent.loop import ALWAYS_ALLOWED
    from .headless import unknown_tool_message

    requested = set(allowed_tools or ()) | set(deps.denied_tools)
    if not requested:
        return None
    known = set(build_agent_registry(deps, depth=0, run_agent=run_agent).names())
    # `runtime.disabled_tools` ile kapatılmış araç geçerli bir addır; "bilinmeyen" denmez.
    known |= ALWAYS_ALLOWED | set(getattr(deps.config.runtime, "disabled_tools", ()))
    unknown = requested - known
    if not unknown:
        return None
    text = unknown_tool_message(unknown, known)
    bus.publish(ErrorOccurred(text, fatal=True))
    return AgentOutcome(final_text=text, messages=[], ok=False)


def _changed_names(tool_context: ToolContext) -> tuple[str, ...]:
    """Değişen yolları kullanıcıya gösterilecek biçimde (köke göreli) ver."""
    from ..tools.files import display_path

    return tuple(display_path(tool_context, path) for path in tool_context.changes.paths)


def open_memory(config: Config, *, root: Path, enabled: bool = True) -> Memory:
    """Belleği aç. Kapalıysa ya da açılamıyorsa boş belleğe düşer."""
    return build_memory(config, root=root) if enabled else null_memory()


def _warn_if_unavailable(memory: Memory, bus: EventBus) -> None:
    """Bellek açılamadıysa kullanıcıya söyle — sessizce öğrenmemek kabul edilemez."""
    if memory.unavailable_reason is not None:
        bus.publish(
            ErrorOccurred(
                messages.MEMORY_UNAVAILABLE.format(reason=memory.unavailable_reason),
                fatal=False,
            )
        )


@dataclass(frozen=True, slots=True)
class Observers:
    """Bir turu izleyen dinleyiciler ve kapanışta yapılacaklar."""

    sinks: tuple[EventSink, ...]
    cost: CostTracker
    tracer: LangfuseTracer
    trace: TraceWriter | None = None

    def finish(self) -> None:
        """Bekleyen izleme kayıtlarını gönder ve izi kapat."""
        self.tracer.flush()
        if self.trace is not None:
            self.trace.close()


def build_observers(
    task: str,
    *,
    renderer: EventSink | None = None,
    as_json: bool = False,
    trace_dir: Path | None = None,
    usage_log: EventSink | None = None,
) -> Observers:
    """Turu izleyecek dinleyicileri kur.

    Sıra önemlidir: render önce gelir ki kullanıcı çıktıyı beklemesin. İzleme ve
    maliyet toplama sessizdir, ekrana bir şey basmaz.

    `trace_dir` verilirse tur kendi JSONL izini bırakır. İz TEŞHİS içindir: bir
    koşunun neden düştüğü sonradan `fusion trace` ile sorulabilsin diye tutulur.
    Yazılamıyorsa tur devam eder; teşhis kaydı işin kendisini durdurmaz.
    """
    cost = CostTracker()
    tracer = LangfuseTracer(task=task)
    sinks: list[EventSink] = []
    if as_json:
        sinks.append(JsonRenderer())
    elif renderer is not None:
        sinks.append(renderer)
    sinks.extend((cost, tracer))
    # Kalıcı kullanım günlüğü (P-056): maliyet toplayıcıyla AYNI olayları dinler.
    if usage_log is not None:
        sinks.append(usage_log)
    trace = open_trace(trace_dir)
    if trace is not None:
        sinks.append(trace)
    return Observers(sinks=tuple(sinks), cost=cost, tracer=tracer, trace=trace)


def open_trace(trace_dir: Path | None) -> TraceWriter | None:
    """Koşu izini aç; kimlik zaman damgasıdır, sıralama da bundan gelir."""
    if trace_dir is None:
        return None
    try:
        return TraceStore(trace_dir).writer(datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    except OSError:
        return None


def _artifact_id() -> str:
    """Oturum artifact dizininin adı — iz kimliğiyle aynı zaman damgası biçimi."""
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")

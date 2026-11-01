"""`fusion -p` koşusu: tur(lar)ı çalıştır, çıktıyı Claude biçiminde yaz.

- `text`: stdout'a YALNIZ nihai cevap (#281); ilerleme `--verbose` ile stderr'e.
- `json`: tek `SDKResultMessage` (#279); koşu içi hata da sonuç nesnesidir (#315).
- `stream-json`: `system/init`, `assistant`/`user` mesajları, `result` (#280).
- `--input-format stream-json`: her kullanıcı satırı bir tur, denetim istekleri (#280;
  bkz. `print_stream`, `print_control`).
- `--json-schema`: cevap şemaya uymazsa tur sınırlı kez yeniden denenir (#301).
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markup import escape

from ..core.errors import FusionError
from ..core.events import EventSink
from ..core.types import Message
from ..engines.agent import dynamic_sections, subagent_prompt
from ..engines.agent.approval import ApprovalMemory, ApprovalMode
from ..engines.agent.child_runs import ChildRuns
from ..engines.agent.loop import AgentOutcome
from ..engines.hooks import lifecycle as hook_lifecycle
from ..observability.usage_log import open_usage_log
from ..providers import beta_headers
from ..tools.capabilities import CapabilityRegistry
from ..ui import print_messages as texts
from ..ui.renderer import ConsoleRenderer
from . import sdk_messages as sdk
from .cleanup import with_web_cleanup
from .headless import OutputFormat
from .print_background import ActivityClock, budget_check, run_then_wait
from .print_options import read_print_prompt, schema_errors
from .print_plan import PrintPlan, PrintRequest, build_plan, plan_extra_system
from .print_runtime import (
    SIGTERM_EXIT_CODE,
    PrintPrompter,
    TerminatedError,
    enable_debug_logging,
    sigterm_as_exception,
)
from .print_session import (
    PrintSession,
    find_pr_session,
    record_turn,
    resolve_print_session,
    snapshot_plan,
)
from .print_setup import run_setup_hooks
from .print_slash import SlashExpansion
from .print_turn import catalog, prepare_turn, turn_tools
from .repl.persona_commands import initial_persona_task
from .sdk_init import CatalogSummary, active_plugin_paths, catalog_summary, init_message
from .sdk_suggestions import model_suggestion
from .session import build_observers, open_memory, run_agent_task

#: Şemaya uymayan yapısal çıktı için en fazla yeniden deneme.
STRUCTURED_RETRIES = 2
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_stderr = Console(stderr=True, highlight=False)


def _warn(text: str) -> None:
    _stderr.print(escape(text))


@dataclass(slots=True)
class _Run:
    """Tek koşunun (bir ya da çok tur) değişken durumu."""

    plan: PrintPlan
    root: Path
    session: PrintSession
    started: float
    stats: sdk.RunStats = field(default_factory=sdk.RunStats)
    history: list[Message] = field(default_factory=list)
    stream: sdk.SdkStream | None = None
    memory: Any = None
    approval: ApprovalMemory = field(default_factory=ApprovalMemory)
    #: Son turun maliyet toplayıcısı (`CostTracker`).
    cost: Any = None
    #: Beceri/ajan kataloğu (koşu boyunca bir kez kurulur).
    capabilities: CapabilityRegistry | None = None
    #: `/beceri` genişletmesinin bu tura eki (#313).
    slash: SlashExpansion | None = None
    #: `--input-format stream-json` denetim kanalı (`print_control.ControlChannel`).
    control: Any = None
    #: `system/init` ve `initialize` için komut/beceri/eklenti keşif bilgisi.
    summary: CatalogSummary = field(default_factory=CatalogSummary)


def run_print(request: PrintRequest) -> int:
    """`-p` koşusunu çalıştır; çıkış kodunu döndür (0 başarı, 1 hata, 143 SIGTERM)."""
    root = Path.cwd()
    try:
        plan = build_plan(request, root=root)
    except ValueError as error:
        _warn(str(error))
        return 1
    for warning in plan.warnings:
        _warn(warning)
    try:
        enable_debug_logging(request.debug, request.debug_file)
    except OSError as error:
        _warn(texts.PRINT_DEBUG_FILE_FAILED.format(path=request.debug_file, error=error))
        return 1
    with (
        sigterm_as_exception(),
        subagent_prompt.appended(plan.subagent_append),
        dynamic_sections.excluded(request.exclude_dynamic),
        beta_headers.enabled(beta_headers.parse(request.betas)),
        hook_lifecycle.observer_scope(),
    ):
        try:
            if request.init_only:
                # Claude `--init-only`: Setup + SessionStart(startup), konuşma yok, çıktı yok.
                run_setup_hooks(
                    plan.config,
                    root,
                    request.setup_triggers,
                    session_id=plan.session_id or "",
                    session_start=True,
                )
                return 0
            return _start(plan, root)
        except TerminatedError:
            return SIGTERM_EXIT_CODE
        except (FusionError, ValueError) as error:
            return _runtime_error(plan, str(error))


def _runtime_error(plan: PrintPlan, text: str, session_id: str = "") -> int:
    """Koşu içi hata: json kiplerinde sonuç nesnesi (stdout), metinde stderr (#315)."""
    if plan.fmt is OutputFormat.TEXT:
        _warn(text)
        return 1
    data = sdk.ResultInput(
        session_id=session_id or plan.session_id or "",
        final_text=text,
        subtype=sdk.SUBTYPE_EXECUTION,
        num_turns=0,
        duration_ms=0,
        stop_reason=None,
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=0.0,
        cost_complete=True,
        errors=(text,),
    )
    _write_json(sdk.result_message(data, sdk.RunStats()))
    return 1


def _write_json(message: object) -> None:
    sys.stdout.write(json.dumps(sdk.redacted(message), ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def _start(plan: PrintPlan, cwd: Path) -> int:
    from .repl import worktrees

    request = plan.request
    root, _tree = worktrees.resolve_launch_root(cwd, request.worktree)
    resume = request.resume
    if request.from_pr:
        resume = find_pr_session(plan.config.memory_dir, root, request.from_pr)
    session = resolve_print_session(
        plan.config.memory_dir,
        root,
        continue_last=request.continue_last,
        resume=resume,
        fork=request.fork_session,
        name=request.name,
        session_id=plan.session_id,
        persist=request.persist,
    )
    plan = snapshot_plan(plan, session, resuming=bool(request.continue_last or resume))
    run = _Run(plan, root, session, time.monotonic(), history=list(session.history))
    run.memory = open_memory(plan.config, root=root, enabled=not request.no_memory)
    if plan.fmt is OutputFormat.STREAM_JSON:
        run.capabilities = catalog(run)
        plugins = () if request.bare or request.safe_mode else active_plugin_paths()
        run.summary = catalog_summary(run.capabilities, plugins)
        run.stream = sdk.SdkStream(
            session.session_id,
            lambda: plan.config.agent.model,
            partial=request.include_partial,
            forward_subagent_text=request.forward_subagent,
            include_hooks=request.include_hooks,
            prompt_suggestions=request.prompt_suggestions,
        )
        run.stream.write(_init(run))
    # `-p --init` / `--maintenance` (#301): konuşmadan önce Setup kancaları (akışta görünür).
    run_setup_hooks(plan.config, root, request.setup_triggers, session_id=session.session_id)
    if plan.stream_input:
        from .print_stream import stream_turns

        return stream_turns(run)
    stdin = getattr(sys.stdin, "buffer", None)
    task, warning = read_print_prompt(request.prompt, stdin, is_tty=sys.stdin.isatty())
    if warning:
        _warn(warning)
    if not task:
        _warn(texts.PRINT_NO_PROMPT)
        return 1
    prepared = prepare_turn(run, task)
    if prepared.reply is not None:
        return _finish(run, task, replied(prepared.reply), None, ())
    return _finish(run, task, *_turn(run, initial_persona_task(plan.persona, prepared.task)))


def replied(text: str) -> AgentOutcome:
    """Modele gitmeden cevaplanan tur (yerleşik komut, kullanılamayan komut)."""
    return AgentOutcome(final_text=text, messages=[], ok=True)


def _init(run: _Run) -> dict[str, object]:
    plan = run.plan
    return init_message(
        session_id=run.session.session_id,
        cwd=str(run.root),
        model=plan.config.agent.model,
        mode=plan.mode,
        mcp_servers=[server.name for server in plan.config.mcp_servers],
        mcp_errors=plan.mcp_errors,
        tools=sorted(plan.selection.allowed or ()),
        agents=[item.name for item in plan.session_agents],
        catalog=run.summary,
    )


def _turn(run: _Run, task: str) -> tuple[AgentOutcome, object | None, tuple[str, ...]]:
    """Turu (ve gerekiyorsa şema yeniden denemelerini) koş: (outcome, yapısal, hatalar)."""
    outcome = _run_once(run, task)
    schema = run.plan.schema
    if schema is None or not outcome.ok:
        return outcome, None, ()
    value, errors = _structured(outcome.final_text, schema)
    for _attempt in range(STRUCTURED_RETRIES):
        if not errors:
            break
        retry = texts.PRINT_SCHEMA_RETRY.format(errors="; ".join(errors[:5]))
        outcome = _run_once(run, retry)
        if not outcome.ok:
            break
        value, errors = _structured(outcome.final_text, schema)
    return outcome, value, errors


def _structured(text: str, schema: dict[str, object]) -> tuple[object | None, tuple[str, ...]]:
    """Önce ham metin JSON denenir; olmazsa ``` çitinin içi (çit JSON dizgesinde de olabilir)."""
    raw = text.strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        fenced = _FENCE.search(raw)
        if fenced is None:
            return None, (f"nihai cevap geçerli bir JSON değil: {error}",)
        try:
            value = json.loads(fenced.group(1).strip())
        except json.JSONDecodeError as inner:
            return None, (f"nihai cevap geçerli bir JSON değil: {inner}",)
    return value, schema_errors(value, schema)


def _run_once(run: _Run, task: str) -> AgentOutcome:
    plan, request = run.plan, run.plan.request
    renderer: EventSink | None = None
    if run.stream is not None:
        renderer = run.stream
    elif plan.fmt is OutputFormat.TEXT and request.verbose:
        renderer = ConsoleRenderer(_stderr, show_progress=True)
    observers = build_observers(
        task,
        renderer=renderer,
        trace_dir=plan.config.memory_dir / "traces",
        usage_log=open_usage_log(plan.config),
    )
    run.cost = observers.cost
    prompter = _prompter(run)
    child_runs = ChildRuns()
    activity = ActivityClock()
    allowed, denied, slash_system = turn_tools(run)
    coro = run_agent_task(
        task,
        plan.config,
        sinks=(*observers.sinks, run.stats, activity),
        prompter_factory=lambda _flush: prompter,
        mode=plan.mode,
        root=run.root,
        home=Path.home(),
        memory=run.memory,
        extra_roots=request.add_dir,
        history=list(run.history),
        extra_system="\n\n".join(p for p in (plan_extra_system(plan), slash_system) if p),
        system_prompt=plan.system_prompt,
        session_persona=plan.persona,
        capabilities=run.capabilities or catalog(run),
        allowed_tools=allowed,
        denied_tools=denied,
        interactive=False,
        approval_memory=run.approval,
        conversation_id=run.session.session_id,
        extra_permission_rules=plan.rules,
        child_runs=child_runs,
    )
    try:
        over = budget_check(observers.cost, request.max_budget_usd)
        main = with_web_cleanup(run_then_wait(coro, child_runs, _warn, activity, over))
        outcome: AgentOutcome = asyncio.run(
            run.control.guard(main) if run.control is not None else main
        )
    finally:
        observers.finish()
    run.history = list(getattr(outcome, "messages", None) or run.history)
    return outcome


def _prompter(run: _Run) -> PrintPrompter:
    """Onay arayüzü: `--permission-prompt-tool` varsa MCP aracı, yoksa kimseye sormaz."""
    name = run.plan.request.permission_prompt_tool
    if not name:
        return PrintPrompter()
    from .print_control import STDIO_PROMPT_TOOL, StdioPrompter

    if name.strip() == STDIO_PROMPT_TOOL:
        return StdioPrompter(run.control) if run.control is not None else PrintPrompter()
    from .print_prompt_tool import PromptToolPrompter, mcp_tool_loader

    return PromptToolPrompter(name, mcp_tool_loader(run.plan.config), root=run.root)


def _finish(
    run: _Run, task: str, outcome: AgentOutcome, structured: object | None, errors: tuple[str, ...]
) -> int:
    """Turu kaydet ve seçili biçimde yaz; çıkış kodunu döndür."""
    plan = run.plan
    final_text = str(getattr(outcome, "final_text", "") or "")
    ok = bool(getattr(outcome, "ok", False)) and bool(final_text.strip())
    record_turn(plan.config.memory_dir, run.root, run.session, task, final_text)
    subtype = sdk.result_subtype(
        ok=ok,
        hit_turn_limit=bool(getattr(outcome, "hit_step_limit", False)),
        stop_reason=getattr(outcome, "stop_reason", None),
    )
    if ok and plan.schema is not None and errors:
        subtype = sdk.SUBTYPE_STRUCTURED
    if plan.fmt is OutputFormat.TEXT:
        if final_text.strip():
            sys.stdout.write(final_text.rstrip("\n") + "\n")
            sys.stdout.flush()
        return 0 if subtype == sdk.SUBTYPE_SUCCESS else 1
    if run.stream is not None:
        run.stream.final_answer(final_text)
    _write_json(
        sdk.result_message(_result_input(run, outcome, subtype, structured, errors), run.stats)
    )
    if run.stream is not None:
        run.stream.after_result(
            lambda: model_suggestion(run.history, plan.config),
            skip=not ok or plan.mode is ApprovalMode.PLAN,
        )
    return 0 if subtype == sdk.SUBTYPE_SUCCESS else 1


def _result_input(
    run: _Run,
    outcome: AgentOutcome,
    subtype: str,
    structured: object | None,
    errors: tuple[str, ...],
) -> sdk.ResultInput:
    cost = run.cost
    total = cost.total if cost is not None else None
    has_structured = run.plan.schema is not None and not errors and structured is not None
    return sdk.ResultInput(
        session_id=run.session.session_id,
        final_text=str(getattr(outcome, "final_text", "") or ""),
        subtype=subtype,
        num_turns=int(getattr(outcome, "model_calls_made", 0) or 0),
        duration_ms=int((time.monotonic() - run.started) * 1000),
        stop_reason=getattr(outcome, "stop_reason", None),
        prompt_tokens=total.prompt_tokens if total is not None else 0,
        completion_tokens=total.completion_tokens if total is not None else 0,
        cost_usd=total.cost_usd if total is not None else 0.0,
        cost_complete=bool(cost.cost_complete) if cost is not None else True,
        structured=structured if has_structured else None,
        has_structured=has_structured,
        errors=errors if subtype != sdk.SUBTYPE_SUCCESS else (),
        cache_read_tokens=getattr(total, "cache_read_tokens", 0) if total is not None else 0,
        cache_creation_tokens=getattr(total, "cache_creation_tokens", 0)
        if total is not None
        else 0,
    )

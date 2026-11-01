"""`fusion -p` koşusu: tur(lar)ı çalıştır, çıktıyı Claude biçiminde yaz.

- `text`: stdout'a YALNIZ nihai cevap (#281); ilerleme `--verbose` ile stderr'e.
- `json`: tek `SDKResultMessage` (#279); koşu içi hata da sonuç nesnesidir (#315).
- `stream-json`: `system/init`, `assistant`/`user` mesajları, `result` (#280).
- `--input-format stream-json`: stdin'deki her `{"type":"user",...}` satırı bir tur (#283).
- `--json-schema`: cevap şemaya uymazsa tur sınırlı kez yeniden denenir (#301).
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from rich.console import Console
from rich.markup import escape

from ..core.errors import FusionError
from ..core.events import EventSink
from ..core.types import Message
from ..engines.agent.approval import ApprovalMemory
from ..engines.agent.loop import AgentOutcome
from ..observability.usage_log import open_usage_log
from ..tools.capabilities import CapabilityRegistry
from ..tools.capability_overrides import registry_from_config
from ..ui import print_messages as texts
from ..ui.renderer import ConsoleRenderer
from . import sdk_messages as sdk
from .cleanup import with_web_cleanup
from .headless import OutputFormat
from .print_options import read_print_prompt, schema_errors
from .print_plan import PrintPlan, PrintRequest, build_plan
from .print_runtime import SIGTERM_EXIT_CODE, PrintPrompter, TerminatedError, sigterm_as_exception
from .print_session import PrintSession, record_turn, resolve_print_session
from .print_slash import SlashExpansion, expand_slash
from .repl.persona_commands import initial_persona_task
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
    with sigterm_as_exception():
        try:
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
    session = resolve_print_session(
        plan.config.memory_dir,
        root,
        continue_last=request.continue_last,
        resume=request.resume,
        fork=request.fork_session,
        name=request.name,
        session_id=plan.session_id,
        persist=request.persist,
    )
    run = _Run(plan, root, session, time.monotonic(), history=list(session.history))
    run.memory = open_memory(plan.config, root=root, enabled=not request.no_memory)
    if plan.fmt is OutputFormat.STREAM_JSON:
        run.stream = sdk.SdkStream(
            session.session_id, lambda: plan.config.agent.model, partial=request.include_partial
        )
        run.stream.write(_init(run))
    if plan.stream_input:
        return _stream_turns(run)
    stdin = getattr(sys.stdin, "buffer", None)
    task, warning = read_print_prompt(request.prompt, stdin, is_tty=sys.stdin.isatty())
    if warning:
        _warn(warning)
    if not task:
        _warn(texts.PRINT_NO_PROMPT)
        return 1
    run.capabilities = _catalog(run)
    if not request.disable_slash:
        run.slash = expand_slash(
            task,
            run.capabilities,
            config=plan.config,
            mode=plan.mode,
            root=run.root,
            session_id=run.session.session_id,
        )
        if run.slash.error:
            reply = AgentOutcome(final_text=run.slash.error, messages=[], ok=True)
            return _finish(run, task, reply, None, ())
        task_to_run = run.slash.task
    else:
        task_to_run = task
    return _finish(run, task, *_turn(run, initial_persona_task(plan.persona, task_to_run)))


def _catalog(run: _Run) -> CapabilityRegistry:
    plan = run.plan
    return registry_from_config(
        plan.config,
        Path.home(),
        run.root,
        session_agents=plan.session_agents,
        extra_roots=plan.request.add_dir,
        headless=True,
    )


def _turn_tools(run: _Run) -> tuple[set[str] | None, frozenset[str], str]:
    """Planın araç kümesi + `/beceri` daraltması: (izinli, yasak, ek sistem)."""
    selection, slash = run.plan.selection, run.slash
    allowed = set(selection.allowed) if selection.allowed is not None else None
    if slash is None:
        return allowed, selection.denied, ""
    if slash.allowed_tools is not None:
        allowed = set(slash.allowed_tools) if allowed is None else allowed & slash.allowed_tools
    return allowed, selection.denied | slash.denied_tools, slash.extra_system


def _init(run: _Run) -> dict[str, object]:
    plan = run.plan
    return sdk.init_message(
        session_id=run.session.session_id,
        cwd=str(run.root),
        model=plan.config.agent.model,
        mode=plan.mode,
        mcp_servers=[server.name for server in plan.config.mcp_servers],
        mcp_errors=plan.mcp_errors,
        tools=sorted(plan.selection.allowed or ()),
        agents=[item.name for item in plan.session_agents],
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
    raw = text.strip()
    fenced = _FENCE.search(raw)
    if fenced is not None:
        raw = fenced.group(1).strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        return None, (f"nihai cevap geçerli bir JSON değil: {error}",)
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
    allowed, denied, slash_system = _turn_tools(run)
    coro = run_agent_task(
        task,
        plan.config,
        sinks=(*observers.sinks, run.stats),
        prompter_factory=lambda _flush: prompter,
        mode=plan.mode,
        root=run.root,
        home=Path.home(),
        memory=run.memory,
        extra_roots=request.add_dir,
        history=list(run.history),
        extra_system="\n\n".join(p for p in (_extra_system(plan), slash_system) if p),
        system_prompt=plan.system_prompt,
        session_persona=plan.persona,
        capabilities=run.capabilities or _catalog(run),
        allowed_tools=allowed,
        denied_tools=denied,
        interactive=False,
        approval_memory=run.approval,
        conversation_id=run.session.session_id,
        extra_permission_rules=plan.rules,
    )
    try:
        outcome = asyncio.run(with_web_cleanup(coro))
    finally:
        observers.finish()
    run.history = list(getattr(outcome, "messages", None) or run.history)
    return outcome


def _prompter(run: _Run) -> PrintPrompter:
    """Onay arayüzü: `--permission-prompt-tool` varsa MCP aracı, yoksa kimseye sormaz."""
    name = run.plan.request.permission_prompt_tool
    if not name:
        return PrintPrompter()
    from .print_prompt_tool import PromptToolPrompter, mcp_tool_loader

    return PromptToolPrompter(name, mcp_tool_loader(run.plan.config), root=run.root)


def _extra_system(plan: PrintPlan) -> str:
    if plan.schema is None:
        return plan.extra_system
    from ..ui import messages

    note = messages.HEADLESS_SCHEMA_INSTRUCTION.format(
        schema=json.dumps(plan.schema, ensure_ascii=False)
    )
    return "\n\n".join(part for part in (plan.extra_system, note) if part)


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
        errors=errors if subtype == sdk.SUBTYPE_STRUCTURED else (),
    )


def _stream_turns(run: _Run) -> int:
    """`--input-format stream-json`: her kullanıcı satırı sırayla bir tur (#283)."""
    code = 0
    for task, raw in _user_messages(sys.stdin):
        if run.plan.request.replay_user and run.stream is not None:
            run.stream.write(sdk.user_message(run.session.session_id, raw))
        code = _finish(run, task, *_turn(run, task))
    return code


def _user_messages(stream: TextIO) -> Iterator[tuple[str, object]]:
    """stdin'den `{"type":"user","message":{"content":...}}` satırları; bozuk satır hata."""
    for line in stream:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(texts.PRINT_STREAM_LINE_INVALID.format(error=error)) from None
        if not isinstance(data, dict) or data.get("type") != "user":
            continue
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        text = _content_text(content)
        if text:
            yield text, content
    return


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n\n".join(part for part in parts if part).strip()
    return ""

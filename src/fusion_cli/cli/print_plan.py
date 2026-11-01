"""`fusion -p` isteğinin doğrulanıp koşuya hazır plana çevrilmesi.

Claude'daki gibi geçersiz bayrak koşu BAŞLAMADAN stderr'e yazılır ve sıfır dışı kodla
çıkılır (`ValueError`). Koşu sırasında oluşan hatalar ise json/stream-json'da sonuç
nesnesi olarak stdout'a düşer (bkz. `print_run`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ..config.loader import load_config
from ..config.models import Config
from ..config.permission_rules import PermissionRule
from ..core.errors import ConfigError
from ..engines.agent.approval import ApprovalMode
from ..engines.agent.team import Persona
from ..tools.capabilities import Capability
from ..ui import print_messages as texts
from . import print_options as opts
from .headless import OutputFormat, parse_output_format
from .print_runtime import BARE_TOOLS, apply_print_limits, apply_session_flags


@dataclass(frozen=True, slots=True)
class PrintRequest:
    """Komut satırından gelen ham `-p` bayrakları."""

    prompt: str = ""
    output_format: str = "text"
    input_format: str = "text"
    json_schema: str | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    tools: str | None = None
    permission_mode: str | None = None
    skip_permissions: bool = False
    permission_prompts: str | None = None
    permission_prompt_tool: str | None = None
    system_prompt: str | None = None
    system_prompt_file: str | None = None
    append_system_prompt: str | None = None
    append_system_prompt_file: str | None = None
    model: str | None = None
    fallback_model: str | None = None
    effort: str | None = None
    settings: str | None = None
    mcp_config: tuple[str, ...] = ()
    strict_mcp_config: bool = False
    verbose: bool = False
    bare: bool = False
    no_memory: bool = False
    add_dir: tuple[Path, ...] = ()
    continue_last: bool = False
    resume: str = ""
    fork_session: bool = False
    session_id: str | None = None
    persist: bool = True
    name: str = ""
    agent: str | None = None
    agents: str = ""
    worktree: str = ""
    include_partial: bool = False
    replay_user: bool = False
    forward_subagent: bool = False
    background: bool = False
    disable_slash: bool = False
    config_set: tuple[str, ...] = ()
    profile: str | None = None
    ignored_flags: tuple[str, ...] = ()
    from_pr: str = ""
    debug: str | None = None
    debug_file: str | None = None


@dataclass(frozen=True, slots=True)
class PrintPlan:
    """Doğrulanmış koşu planı."""

    request: PrintRequest
    config: Config
    fmt: OutputFormat
    stream_input: bool
    mode: ApprovalMode
    schema: dict[str, object] | None
    selection: opts.ToolSelection
    rules: tuple[PermissionRule, ...]
    system_prompt: str | None
    extra_system: str
    session_id: str | None
    mcp_errors: tuple[dict[str, str], ...] = ()
    persona: Persona | None = None
    session_agents: tuple[Capability, ...] = ()
    warnings: tuple[str, ...] = ()


def _check_formats(request: PrintRequest) -> tuple[OutputFormat, bool]:
    fmt = parse_output_format(request.output_format)
    raw_input = request.input_format.strip().lower()
    if raw_input not in ("text", "stream-json"):
        raise ValueError(texts.PRINT_UNKNOWN_INPUT_FORMAT.format(given=request.input_format))
    stream_input = raw_input == "stream-json"
    if fmt is OutputFormat.STREAM_JSON and not request.verbose:
        raise ValueError(texts.PRINT_STREAM_JSON_NEEDS_VERBOSE)
    if stream_input and fmt is not OutputFormat.STREAM_JSON:
        raise ValueError(texts.PRINT_INPUT_STREAM_NEEDS_OUTPUT_STREAM)
    if request.background:
        raise ValueError(texts.PRINT_BG_WITH_PRINT)
    prompts = (request.permission_prompts or "host").strip().lower()
    if prompts not in ("host", "none"):
        raise ValueError(texts.PRINT_UNKNOWN_PERMISSION_PROMPTS.format(given=prompts))
    return fmt, stream_input


def _build_config(
    request: PrintRequest,
) -> tuple[Config, tuple[dict[str, str], ...], dict[str, object]]:
    try:
        config = apply_session_flags(load_config(), request.config_set, request.profile)
    except ConfigError as error:
        raise ValueError(str(error)) from None
    settings = opts.load_settings(request.settings)
    model = request.model or _settings_text(settings, "model")
    config = opts.apply_model(config, model, request.fallback_model)
    if request.effort:
        config = _with_effort(config, request.effort)
    config, mcp_errors = opts.load_mcp_configs(
        config, request.mcp_config, strict=request.strict_mcp_config
    )
    config = apply_print_limits(
        config,
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        bare=request.bare,
    )
    return config, mcp_errors, settings


def _settings_text(settings: dict[str, object], key: str) -> str | None:
    value = settings.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _with_effort(config: Config, raw: str) -> Config:
    from ..core.reasoning import ReasoningEffort

    try:
        effort = ReasoningEffort(raw.strip().lower())
    except ValueError:
        valid = ", ".join(item.value for item in ReasoningEffort)
        raise ValueError(f"Bilinmeyen --effort değeri: {raw}. Geçerli: {valid}") from None
    return replace(config, runtime=replace(config.runtime, reasoning_effort=effort))


def build_plan(request: PrintRequest, *, root: Path) -> PrintPlan:
    """İsteği doğrula; her hata `ValueError` (komut stderr'e yazıp 1 ile çıkar)."""
    fmt, stream_input = _check_formats(request)
    schema = opts.parse_json_schema(request.json_schema)
    session_id = opts.checked_session_id(request.session_id)
    mode = opts.parse_permission_mode(
        request.permission_mode, skip_permissions=request.skip_permissions
    )
    config, mcp_errors, settings = _build_config(request)
    selection = opts.tool_selection(
        request.allowed_tools,
        request.disallowed_tools,
        request.tools,
        mcp_servers=tuple(server.name for server in config.mcp_servers),
    )
    if request.bare:
        allowed = selection.allowed
        bare = allowed & BARE_TOOLS if allowed is not None else BARE_TOOLS
        selection = replace(selection, allowed=bare)
    replacement, extra = opts.system_prompts(
        system_prompt=request.system_prompt,
        system_prompt_file=request.system_prompt_file,
        append=request.append_system_prompt,
        append_file=request.append_system_prompt_file,
    )
    warnings = [texts.PRINT_UNSUPPORTED_FLAG.format(flag=flag) for flag in request.ignored_flags]
    if selection.unmapped:
        warnings.append(texts.PRINT_UNMAPPED_TOOLS.format(names=", ".join(selection.unmapped)))
    plan = PrintPlan(
        request=request,
        config=config,
        fmt=fmt,
        stream_input=stream_input,
        mode=mode,
        schema=schema,
        selection=selection,
        rules=(*selection.rules, *opts.settings_rules(settings)),
        system_prompt=replacement,
        extra_system=extra,
        session_id=session_id,
        mcp_errors=mcp_errors,
        warnings=tuple(warnings),
    )
    return _with_agent(plan, root=root)


def _with_agent(plan: PrintPlan, *, root: Path) -> PrintPlan:
    """`--agents` JSON tanımları ve `--agent <ad>` baş ajanı (REPL ile aynı etki)."""
    from ..engines.agent.team_settings import validate_agent_hooks
    from ..tools.agent_catalog_launch import session_agents_from_json
    from .headless import resolve_agent
    from .repl.persona_commands import persona_turn

    request = plan.request
    try:
        agents = session_agents_from_json(request.agents, root=root) if request.agents else ()
        name = request.agent or plan.config.agent_launch.default_agent
        if not name:
            return replace(plan, session_agents=agents)
        persona = resolve_agent(
            name,
            home=Path.home(),
            root=root,
            managed_roots=tuple(Path(v) for v in plan.config.agent_launch.managed_agent_roots),
            session_agents=agents,
        )
        validate_agent_hooks(persona)
    except ConfigError as error:
        raise ValueError(str(error)) from None
    turn = persona_turn(persona)
    selection = plan.selection
    if turn.allowed_tools is not None:
        narrowed = frozenset(turn.allowed_tools)
        allowed = narrowed if selection.allowed is None else selection.allowed & narrowed
        selection = replace(selection, allowed=allowed)
    selection = replace(selection, denied=selection.denied | turn.denied_tools)
    extra = "\n\n".join(part for part in (turn.extra_system, plan.extra_system) if part)
    return replace(
        plan,
        persona=persona,
        session_agents=agents,
        selection=selection,
        system_prompt=plan.system_prompt or turn.system_prompt,
        extra_system=extra,
    )

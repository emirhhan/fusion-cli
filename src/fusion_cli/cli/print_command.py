"""`fusion -p` — Claude Code `claude -p/--print` başsız kipi (#275 ve headless-cli alanı).

Kök komut satırı `print_argv.ClaudeArgsGroup` ile bu gizli alt komuta çevrilir; bayrak
adları ve anlamları Claude Code'unkilerdir (`--output-format`, `--permission-mode`,
`--allowedTools`, `--tools`, `--model`, `-c/-r`, `--session-id`, `--json-schema`…).
Bayrakların yorumu `print_options`, koşu ortamı `print_runtime`, çıktı biçimi
`sdk_messages`, oturum `print_session`, koşunun kendisi `print_run` modülündedir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .print_plan import PrintRequest
from .print_run import run_print


def print_command(
    prompt: Annotated[str, typer.Argument(help="İstem; boru stdin'i istemle birleşir.")] = "",
    output_format: Annotated[str, typer.Option("--output-format")] = "text",
    input_format: Annotated[str, typer.Option("--input-format")] = "text",
    json_schema: Annotated[str | None, typer.Option("--json-schema")] = None,
    max_turns: Annotated[int | None, typer.Option("--max-turns", min=1)] = None,
    max_budget_usd: Annotated[float | None, typer.Option("--max-budget-usd", min=0.0)] = None,
    allowed_tools: Annotated[
        list[str] | None, typer.Option("--allowedTools", "--allowed-tools")
    ] = None,
    disallowed_tools: Annotated[
        list[str] | None, typer.Option("--disallowedTools", "--disallowed-tools")
    ] = None,
    tools: Annotated[str | None, typer.Option("--tools")] = None,
    permission_mode: Annotated[str | None, typer.Option("--permission-mode", "--mode")] = None,
    skip_permissions: Annotated[bool, typer.Option("--dangerously-skip-permissions")] = False,
    allow_skip: Annotated[bool, typer.Option("--allow-dangerously-skip-permissions")] = False,
    permission_prompts: Annotated[str | None, typer.Option("--permission-prompts")] = None,
    permission_prompt_tool: Annotated[str | None, typer.Option("--permission-prompt-tool")] = None,
    system_prompt: Annotated[str | None, typer.Option("--system-prompt")] = None,
    system_prompt_file: Annotated[str | None, typer.Option("--system-prompt-file")] = None,
    append_system_prompt: Annotated[str | None, typer.Option("--append-system-prompt")] = None,
    append_system_prompt_file: Annotated[
        str | None, typer.Option("--append-system-prompt-file")
    ] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    fallback_model: Annotated[str | None, typer.Option("--fallback-model")] = None,
    effort: Annotated[str | None, typer.Option("--effort")] = None,
    settings: Annotated[str | None, typer.Option("--settings")] = None,
    setting_sources: Annotated[str | None, typer.Option("--setting-sources")] = None,
    mcp_config: Annotated[list[str] | None, typer.Option("--mcp-config")] = None,
    strict_mcp_config: Annotated[bool, typer.Option("--strict-mcp-config")] = False,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", hidden=True)] = False,
    bare: Annotated[bool, typer.Option("--bare")] = False,
    no_memory: Annotated[bool, typer.Option("--no-memory")] = False,
    add_dir: Annotated[
        list[Path] | None,
        typer.Option("--add-dir", exists=True, file_okay=False, dir_okay=True),
    ] = None,
    continue_last: Annotated[bool, typer.Option("--continue", "-c")] = False,
    resume: Annotated[str, typer.Option("--resume", "-r")] = "",
    fork_session: Annotated[bool, typer.Option("--fork-session")] = False,
    session_id: Annotated[str | None, typer.Option("--session-id")] = None,
    no_persist: Annotated[bool, typer.Option("--no-session-persistence")] = False,
    name: Annotated[str, typer.Option("--name", "-n")] = "",
    agent: Annotated[str | None, typer.Option("--agent")] = None,
    agents: Annotated[str, typer.Option("--agents")] = "",
    worktree: Annotated[str, typer.Option("--worktree", "-w")] = "",
    include_partial: Annotated[bool, typer.Option("--include-partial-messages")] = False,
    replay_user: Annotated[bool, typer.Option("--replay-user-messages")] = False,
    include_hooks: Annotated[bool, typer.Option("--include-hook-events")] = False,
    forward_subagent: Annotated[bool, typer.Option("--forward-subagent-text")] = False,
    prompt_suggestions: Annotated[bool, typer.Option("--prompt-suggestions")] = False,
    background: Annotated[bool, typer.Option("--bg")] = False,
    from_pr: Annotated[str | None, typer.Option("--from-pr")] = None,
    debug: Annotated[str | None, typer.Option("--debug")] = None,
    debug_file: Annotated[str | None, typer.Option("--debug-file")] = None,
    plugin_dir: Annotated[list[str] | None, typer.Option("--plugin-dir")] = None,
    betas: Annotated[list[str] | None, typer.Option("--betas")] = None,
    disable_slash: Annotated[bool, typer.Option("--disable-slash-commands")] = False,
    exclude_dynamic: Annotated[
        bool, typer.Option("--exclude-dynamic-system-prompt-sections")
    ] = False,
    config_set: Annotated[list[str] | None, typer.Option("--set")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    """Claude Code `-p`: istemi etkileşimsiz çalıştır, cevabı yaz ve çık."""
    ignored = {
        "--include-hook-events": include_hooks,
        "--forward-subagent-text": forward_subagent,
        "--prompt-suggestions": prompt_suggestions,
        "--debug": debug is not None,
        "--debug-file": debug_file is not None,
        "--plugin-dir": bool(plugin_dir),
        "--betas": bool(betas),
        "--exclude-dynamic-system-prompt-sections": exclude_dynamic,
        "--setting-sources": setting_sources is not None,
        "--from-pr": from_pr is not None,
    }
    request = PrintRequest(
        prompt=prompt,
        output_format=output_format,
        input_format=input_format,
        json_schema=json_schema,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        allowed_tools=tuple(allowed_tools or ()),
        disallowed_tools=tuple(disallowed_tools or ()),
        tools=tools,
        permission_mode=permission_mode,
        skip_permissions=skip_permissions,
        permission_prompts=permission_prompts,
        permission_prompt_tool=permission_prompt_tool,
        system_prompt=system_prompt,
        system_prompt_file=system_prompt_file,
        append_system_prompt=append_system_prompt,
        append_system_prompt_file=append_system_prompt_file,
        model=model,
        fallback_model=fallback_model,
        effort=effort,
        settings=settings,
        mcp_config=tuple(mcp_config or ()),
        strict_mcp_config=strict_mcp_config,
        verbose=verbose and not quiet,
        bare=bare,
        no_memory=no_memory or bare,
        add_dir=tuple(add_dir or ()),
        continue_last=continue_last,
        resume=resume,
        fork_session=fork_session,
        session_id=session_id,
        persist=not no_persist,
        name=name,
        agent=agent,
        agents=agents,
        worktree=worktree,
        include_partial=include_partial,
        replay_user=replay_user,
        background=background,
        disable_slash=disable_slash,
        config_set=tuple(config_set or ()),
        profile=profile,
        ignored_flags=tuple(flag for flag, given in ignored.items() if given),
    )
    del allow_skip  # Claude: bypass'ı yalnız seçilebilir yapar; -p'de etkisi yok
    raise typer.Exit(run_print(request))

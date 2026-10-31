"""`fusion hooks` — kancaları listele ve örnek olayla dene (P-009; Claude Code `/hooks`).

    fusion hooks list [--json]                     tüm katmanlardaki kancalar ve durumları
    fusion hooks test PreToolUse --tool Bash --input '{"command": "rm -rf x"}'
    fusion hooks test UserPromptSubmit --prompt "merhaba"

`test` eşleşen kancaları GERÇEKTEN çalıştırır (kullanıcının kendi komutları) ve birleşik
kararı gösterir; engel varsa çıkış kodu 2.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from ..config.hooks import hook_rows
from ..config.loader import load_config
from ..core.hooks.events import HookEvent, HookVerdict, parse_event
from ..engines.agent.hook_bridge import tool_hook_fields
from ..engines.hooks.session import HookSession, open_hook_session
from ..tools.permission_match import claude_tool_names
from ..ui import messages, theme
from .hooks_view import hook_list_lines

app = typer.Typer(no_args_is_help=True, help="Kancaları (hooks) listele ve dene.")
console = Console()

_TOOL_EVENTS = frozenset(
    {HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE, HookEvent.POST_TOOL_USE_FAILURE}
)
PathOption = Annotated[
    Path, typer.Option("--path", help="Proje kökü (varsayılan: bulunduğun dizin).")
]


@app.command("list")
def list_hooks(
    as_json: Annotated[bool, typer.Option("--json", help="Satırları JSON olarak yaz.")] = False,
    path: PathOption = Path(),
) -> None:
    """Tüm katmanlardaki kancalar: olay · eşleştirici · komut · kaynak · durum."""
    hooks = open_hook_session(path.resolve(), load_config()).refresh()
    if as_json:
        payload = {
            "kapali": hooks.disabled_reason,
            "guvensiz_katmanlar": list(hooks.untrusted_layers),
            "yok_sayilan_kapatma": list(hooks.ignored_disable_layers),
            "kancalar": [asdict(row) for row in hook_rows(hooks)],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for line in hook_list_lines(hooks):
        console.print(escape(line))


@app.command("test")
def test_hook(
    event: Annotated[str, typer.Argument(help="Olay adı: PreToolUse, Stop, SessionStart…")],
    tool: Annotated[str, typer.Option("--tool", help="Araç adı (Fusion ya da Claude).")] = "Bash",
    tool_input: Annotated[
        str, typer.Option("--input", help="Araç argümanları (JSON nesnesi).")
    ] = "{}",
    prompt: Annotated[str, typer.Option("--prompt", help="UserPromptSubmit istemi.")] = "",
    path: PathOption = Path(),
) -> None:
    """Eşleşen kancaları örnek bir olayla çalıştır ve kararı göster."""
    parsed = parse_event(event)
    if parsed is None:
        names = ", ".join(item.value for item in HookEvent)
        _error(messages.HOOKS_TEST_UNKNOWN_EVENT.format(given=event, events=names))
        raise typer.Exit(code=2)
    try:
        arguments: object = json.loads(tool_input)
    except ValueError as error:
        arguments = error
    if not isinstance(arguments, dict):
        _error(messages.HOOKS_TEST_BAD_INPUT.format(error=arguments))
        raise typer.Exit(code=2)
    session = open_hook_session(path.resolve(), load_config())
    session.refresh()
    verdict = asyncio.run(_emit(session, parsed, tool, arguments, prompt))
    _print_verdict(parsed, verdict)
    if verdict.blocked:
        raise typer.Exit(code=2)


async def _emit(
    session: HookSession,
    event: HookEvent,
    tool: str,
    arguments: dict[str, object],
    prompt: str,
) -> HookVerdict:
    if event in _TOOL_EVENTS:
        return await session.emit(
            event, subjects=claude_tool_names(tool), fields=tool_hook_fields(tool, arguments)
        )
    fields = {"prompt": prompt} if event is HookEvent.USER_PROMPT_SUBMIT else {}
    return await session.emit(event, subjects=("startup", "manual", "other", ""), fields=fields)


def _print_verdict(event: HookEvent, verdict: HookVerdict) -> None:
    if verdict.ran == 0:
        console.print(escape(messages.HOOKS_TEST_NONE.format(event=event.value)))
        return
    console.print(
        escape(
            messages.HOOKS_TEST_RESULT.format(
                event=event.value,
                ran=verdict.ran,
                blocked="evet" if verdict.blocked else "hayır",
                permission=verdict.permission or "—",
                halt="evet" if verdict.halt else "hayır",
            )
        )
    )
    for label, value in (
        ("gerekçe", verdict.reason or verdict.stop_reason),
        ("bağlam", verdict.context_text),
        ("değişen girdi", _json(verdict.updated_input)),
    ):
        if value:
            console.print(escape(f"  {label}: {value}"))
    for text in verdict.system_messages:
        console.print(escape(f"  {messages.HOOKS_SYSTEM.format(text=text)}"))
    for detail in verdict.errors:
        _error("  " + messages.HOOKS_ERROR.format(detail=detail), color=theme.WARN)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False) if value else ""


def _error(text: str, *, color: str = theme.ERROR) -> None:
    console.print(f"[{color}]{escape(text)}[/{color}]")

"""`fusion agents` görünümü ve `fusion agent --bg` (Claude Code `claude agents` / `--bg`; P-048).

`fusion agents` (argümansız) görevleri gruplu tabloda listeler; `--izle` tabloyu canlı
tazeler (Ctrl+C görünümü kapatır, görevler sürer). Alt komutlar REPL `/tasks` ile aynı
işleri yapar: goster, durdur, mesaj, cevapla, sil, temizle.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.live import Live
from rich.markup import escape

from ..config.loader import load_config
from ..core.background_store import BackgroundTaskStore
from ..core.background_tasks import BackgroundTask, BackgroundTaskError, TaskOptions
from ..core.errors import FusionError
from ..tools import agent_tasks
from ..ui import background_messages as texts
from ..ui import theme
from ..ui.background_view import task_detail, task_table
from . import headless
from .background_worker import run_worker

console = Console()
error_console = Console(stderr=True)

#: `--izle` tazeleme aralığı (saniye).
WATCH_REFRESH_S = 1.0

app = typer.Typer(
    invoke_without_command=True,
    help="Arka plan ajan görevlerini izle ve yönet (fusion agent --bg ile başlar).",
)


def _store() -> BackgroundTaskStore:
    return agent_tasks.task_store(load_config().memory_dir)


def _fail(error: BackgroundTaskError) -> typer.Exit:
    error_console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
    return typer.Exit(1)


def _resolve(query: str) -> tuple[BackgroundTaskStore, BackgroundTask]:
    store = _store()
    try:
        return store, store.resolve(query)
    except BackgroundTaskError as error:
        raise _fail(error) from None


@app.callback()
def agents(
    ctx: typer.Context,
    watch: bool = typer.Option(False, "--izle", "-w", help="Tabloyu canlı tazele."),
    as_json: bool = typer.Option(False, "--json", help="Görevleri JSON satırları olarak yaz."),
    every_project: bool = typer.Option(False, "--tum", "-a", help="Bütün projelerin görevleri."),
) -> None:
    """Arka plan görevlerini listele (girdi bekleyen → çalışan → biten)."""
    if ctx.invoked_subcommand is not None:
        return
    store = _store()
    root = None if every_project else Path.cwd()
    if as_json:
        for task in store.tasks(root=root):
            typer.echo(json.dumps(task.to_dict(), ensure_ascii=False))
        return
    if not watch:
        console.print(task_table(store.tasks(root=root)))
        return
    console.print(f"[{theme.DIM}]{texts.BG_CLI_WATCH_HINT}[/{theme.DIM}]")
    try:
        with Live(task_table(store.tasks(root=root)), console=console, auto_refresh=False) as live:
            while True:
                time.sleep(WATCH_REFRESH_S)
                live.update(task_table(store.tasks(root=root)), refresh=True)
    except KeyboardInterrupt:
        return


@app.command("goster")
def show(kimlik: str = typer.Argument(..., help="Görev kimliği ya da adı.")) -> None:
    """Görevin ayrıntısı, son sonucu ve son olayları."""
    store, task = _resolve(kimlik)
    console.print(
        task_detail(
            task,
            store.read_result(task.id),
            agent_tasks.log_tail(store, task.id),
            question=store.pending_question(task.id),
        ),
        markup=False,
        highlight=False,
    )


@app.command("durdur")
def stop(
    kimlik: str = typer.Argument(...),
    force: bool = typer.Option(False, "--zorla", help="İşçi süreci kimliği doğrulanırsa öldür."),
) -> None:
    """Görevi durdur (önce işbirlikli durdurma isteği)."""
    store, task = _resolve(kimlik)
    try:
        updated = agent_tasks.stop_task(store, task, force=force)
    except BackgroundTaskError as error:
        raise _fail(error) from None
    console.print(texts.BG_STOP_REQUESTED.format(name=updated.name))


@app.command("mesaj")
def send(kimlik: str = typer.Argument(...), metin: str = typer.Argument(...)) -> None:
    """Göreve devam mesajı gönder; bitmişse aynı konuşmayla yeniden başlar."""
    store, task = _resolve(kimlik)
    try:
        updated = agent_tasks.send_to_task(store, task, metin, sender="terminal")
    except BackgroundTaskError as error:
        raise _fail(error) from None
    console.print(texts.BG_SENT.format(name=updated.name, status=updated.status.value))


@app.command("cevapla")
def answer(
    kimlik: str = typer.Argument(...),
    cevap: str = typer.Argument(..., help="evet | hayir | oturum ya da soru için metin."),
) -> None:
    """Girdi bekleyen görevin onay/sorusunu cevapla."""
    store, task = _resolve(kimlik)
    try:
        agent_tasks.answer_task(store, task, cevap)
    except BackgroundTaskError as error:
        raise _fail(error) from None
    console.print(texts.BG_ANSWERED.format(name=task.name))


@app.command("sil")
def remove(kimlik: str = typer.Argument(...)) -> None:
    """Bitmiş görevin kaydını sil."""
    store, task = _resolve(kimlik)
    try:
        store.remove(task.id)
    except BackgroundTaskError as error:
        raise _fail(error) from None
    console.print(texts.BG_REMOVED.format(name=task.name))


@app.command("temizle")
def clean() -> None:
    """Bütün bitmiş görev kayıtlarını sil."""
    store = _store()
    finished = [task for task in store.tasks() if not task.is_active]
    for task in finished:
        store.remove(task.id)
    console.print(texts.BG_CLEANED.format(count=len(finished)))


@dataclass(frozen=True, slots=True)
class BackgroundFlags:
    """`fusion agent --bg` ile verilen ve işçiye TAŞINAN bayraklar (P-048)."""

    mode: str
    agent: str = ""
    name: str = ""
    max_turns: int | None = None
    max_budget_usd: float | None = None
    allowed_tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    append_system_prompt: str | None = None
    add_dir: tuple[Path, ...] = ()
    worktree: str = ""
    no_memory: bool = False
    bare: bool = False
    config_overrides: tuple[str, ...] = ()
    profile: str = ""


def unsupported_background_flag(
    *, output_format: str, as_json: bool, json_schema: Path | None, permission_channel: str | None
) -> str | None:
    """`--bg` ile ANLAMSIZ bayrak (sonuç stdout'a değil göreve yazılır); yoksa None.

    Ölçüldü (31 Ekim): bu bayraklar `--bg` ile hata vermeden düşüyordu.
    """
    if as_json or output_format.strip().lower() != "text":
        return "--output-format/--json"
    if json_schema is not None:
        return "--json-schema"
    if permission_channel:
        return "--permission-channel"
    return None


def cli_task_options(flags: BackgroundFlags) -> TaskOptions:
    """Bayrakları işçinin uygulayacağı kısıtlara çevir (Claude Code adları da tanınır)."""
    allowed = headless.parse_tool_list(flags.allowed_tools)
    denied = headless.parse_tool_list(flags.disallowed_tools) or frozenset()
    return TaskOptions(
        allowed_tools=(
            tuple(sorted(headless.map_claude_tool_names(allowed))) if allowed is not None else None
        ),
        denied_tools=tuple(sorted(headless.map_claude_tool_names(denied))),
        extra_roots=tuple(str(path.expanduser().resolve()) for path in flags.add_dir),
        extra_system=flags.append_system_prompt or "",
        max_budget_usd=float(flags.max_budget_usd or 0.0),
        memory=not flags.no_memory,
        bare=flags.bare,
        config_overrides=flags.config_overrides,
        profile=flags.profile,
    )


def start_from_cli(task: str, flags: BackgroundFlags) -> BackgroundTask:
    """`fusion agent --bg`: görevi arka planda başlat (sahipsiz; sonuç `fusion agents`'ta).

    `--worktree` ağacı başlatmadan ÖNCE açılır ve görevin kökü olur; diğer kısıtlar
    `TaskOptions` ile işçide uygulanır. `--mode bypass` açıkça istendiyse korunur (miras
    değil, kullanıcının kendi seçimi).
    """
    from .repl import worktrees

    config = load_config()
    try:
        root, _tree = worktrees.resolve_launch_root(Path.cwd(), flags.worktree)
    except FusionError as error:
        error_console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
        raise typer.Exit(1) from None
    request = agent_tasks.LaunchRequest(
        prompt=task,
        root=root,
        name=flags.name,
        origin="cli",
        mode=flags.mode,
        agent=flags.agent,
        max_turns=flags.max_turns or 0,
        options=cli_task_options(flags),
    )
    try:
        return agent_tasks.start_with_settings(config.runtime, config.memory_dir, request)
    except BackgroundTaskError as error:
        raise _fail(error) from None


def worker_command(
    kimlik: Annotated[str, typer.Argument()],
    dizin: Annotated[Path, typer.Option("--dizin")],
) -> None:
    """Gizli: arka plan görevinin işçi süreci (paketlenmiş uygulama için)."""
    raise typer.Exit(run_worker(dizin, kimlik))

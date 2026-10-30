"""Typer giriş noktası.

Komut fonksiyonları ince tutulur: girdiyi çözer, oturumu çağırır, sonucu sunar.
İş mantığı burada bulunmaz (RULES.md "UI ve CLI").

Beklenen hatalar (`FusionError`) tek bir sınırda yakalanır ve kullanıcıya Türkçe,
anlaşılır bir mesajla gösterilir; stack trace kullanıcıya basılmaz.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import sys
from collections.abc import Coroutine
from dataclasses import fields, replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, TypeVar

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .. import __version__
from ..config.keys import detect
from ..config.loader import load_config
from ..config.models import Config
from ..config.paths import user_data_dir
from ..config.readiness import Readiness, evaluate
from ..core.errors import FusionError
from ..core.tools import ToolContext
from ..core.types import ModelSpec, VerdictSource
from ..core.worktree import Worktree, WorktreeSwitch
from ..engines.agent.approval import ApprovalMemory, ApprovalMode, parse_mode
from ..ui import messages, theme
from .app_host import AppHostDependencies

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi
    from .doctor import DoctorReport
from ..ui.renderer import ConsoleRenderer
from ..ui.tables import cost_summary
from . import (
    capability_commands,
    eval_commands,
    knowledge_commands,
    memory_commands,
    paperclip_command,
    prompt_opt_commands,
    trash_commands,
)
from .cleanup import with_web_cleanup
from .prompter import ConsolePrompter
from .repl import run_repl, session_resume, worktrees
from .rule_notices import attach_rule_writer, print_rule_notices
from .session import Observers, build_observers, open_memory, run_agent_task, run_task
from .setup_command import run_setup

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    # Beklenmeyen istisnada zengin traceback YEREL DEĞİŞKENLERİ basmaz: `session.py`
    # yerelleri arasında config, ortam görüntüsü ve anahtar içeren yapılar var (L1-12).
    pretty_exceptions_show_locals=False,
    help="Ücretsiz LLM'lerle çalışan agentic CLI. Argümansız çalıştırılırsa REPL açılır.",
)
config_app = typer.Typer(no_args_is_help=True, help="Yapılandırmayı görüntüle.")
app.add_typer(config_app, name="config")
app.add_typer(memory_commands.app, name="memory")
app.add_typer(knowledge_commands.app, name="knowledge")
app.add_typer(trash_commands.app, name="cop")
app.add_typer(capability_commands.app, name="yetenek")
app.add_typer(eval_commands.eval_app, name="eval")
app.add_typer(prompt_opt_commands.prompt_opt_app, name="prompt-opt")
app.command("paperclip")(paperclip_command.paperclip)

console = Console()
#: Hata satırları stdout'a DEĞİL stderr'e gider. `fusion mcp` (MCP protokolü), `fusion app`
#: (satır satır JSON) ve `run --json | jq` stdout'u protokol için kullanır; oraya düşen düz
#: metin istemcide ayrıştırma hatasıdır (L1-11).
error_console = Console(stderr=True)
#: `fusion mcp-tools` sunuculara bağlanıp araç keşfederken en fazla bekleyeceği süre (sn).
MCP_TOOLS_TIMEOUT_S = 60.0

T = TypeVar("T")


#: Yapılandırmadaki `task_model_map` ile aynı anahtarlar.
TASK_TYPES = ("general", "code", "reasoning", "agent")


@app.callback()
def main_callback(
    ctx: typer.Context,
    add_dir: Annotated[
        list[Path] | None,
        typer.Option(
            "--add-dir",
            help="Proje kökünün YANINDA erişime açılacak dizin. Birden çok kez verilebilir.",
        ),
    ] = None,
    continue_last: Annotated[
        bool,
        typer.Option("--continue", "-c", help="Bu projedeki son Fusion sohbetini sürdür."),
    ] = False,
    resume: Annotated[
        str,
        typer.Option(
            "--resume", "-r", help="Kimliği, adı ya da kimlik öneki verilen sohbeti sürdür."
        ),
    ] = "",
    fork_session: Annotated[
        bool,
        typer.Option(
            "--fork-session",
            help="Sürdürülen sohbeti kopyalayıp yeni kimlikle aç; özgün sohbet değişmez.",
        ),
    ] = False,
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Sohbete ad ver (/resume listesinde ve --resume <ad>)."),
    ] = "",
    worktree: Annotated[
        str,
        typer.Option(
            "--worktree",
            "-w",
            help="Git çalışma ağacında çalış: .fusion/worktrees/<ad>, dal worktree-<ad>.",
        ),
    ] = "",
) -> None:
    """Argümansız çağrıldığında interaktif oturumu başlat."""
    if ctx.invoked_subcommand is not None:
        return
    config = load_config()
    # Kapı `evaluate` ile: yalnız Ollama/yerel uç ya da başka sağlayıcıyla çalışan kullanıcı,
    # OpenRouter/NIM anahtarı yok diye REPL'e hiç girememeliydi (L1-13). Anahtarsız VARSAYILAN
    # kurulumda agent rolü kullanılamaz, `NOT_READY` olur ve eski davranış korunur.
    if evaluate(config, detect()).state is Readiness.NOT_READY and not config.web_sessions:
        # Anahtarsız açılışta REPL'i başlatmak, kullanıcıyı her turda "hiçbir model
        # yanıt veremedi" hatasına sürüklerdi. Eksik olan şey söylenir.
        console.print(f"[{theme.WARN}]{messages.SETUP_NO_KEYS}[/{theme.WARN}]")
        raise typer.Exit(1)
    try:
        root, tree = worktrees.resolve_launch_root(Path.cwd(), worktree)
        target = session_resume.resolve_launch(
            config.memory_dir,
            root,
            continue_last=continue_last,
            resume=resume,
            fork=fork_session,
            name=name,
        )
    except FusionError as error:
        error_console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
        raise typer.Exit(1) from None
    if tree is not None and worktree.strip():
        _print_worktree_notice(tree)
    exit_code = asyncio.run(
        with_web_cleanup(
            run_repl(
                config,
                memory=open_memory(config, root=root),
                root=root,
                console=console,
                extra_roots=tuple(add_dir or ()),
                resume=target,
                worktree=tree,
            )
        )
    )
    raise typer.Exit(exit_code)


def _print_worktree_notice(tree: Worktree) -> None:
    text = messages.WORKTREE_ENTERED.format(path=tree.path, branch=tree.branch)
    console.print(f"[{theme.DIM}]{escape(text)}[/{theme.DIM}]")


@app.command()
def run(
    task: str = typer.Argument(..., help="Modellere verilecek görev ya da soru."),
    task_type: str = typer.Option(
        "general", "--type", "-t", help=f"Görev tipi: {' | '.join(TASK_TYPES)}"
    ),
    show_all: bool = typer.Option(False, "--all", help="Tüm aday cevaplarını göster."),
    no_synthesis: bool = typer.Option(
        False, "--no-synthesis", help="Sentezi kapat; hakemin seçtiği cevabı göster."
    ),
    no_memory: bool = typer.Option(
        False, "--no-memory", help="Belleği kullanma ve yazma (öğrenme kapalı)."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Olayları satır satır JSON olarak yaz (betikler için)."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="İlerleme satırlarını gizle."),
) -> None:
    """Görevi tüm adaylara paralel sor, hakem ve sentezle en iyi cevabı üret."""
    if not task.strip():
        raise typer.BadParameter(messages.RUN_EMPTY_TASK)
    if task_type not in TASK_TYPES:
        raise typer.BadParameter(
            messages.RUN_UNKNOWN_TASK_TYPE.format(given=task_type, valid=", ".join(TASK_TYPES))
        )

    config = load_config()
    renderer = ConsoleRenderer(
        console, show_progress=not quiet, show_all_answers=show_all, show_call_details=True
    )
    observers = build_observers(
        task, renderer=renderer, as_json=as_json, trace_dir=config.memory_dir / "traces"
    )
    result = _run_observed(
        with_web_cleanup(
            run_task(
                task,
                config,
                sinks=observers.sinks,
                task_type=task_type,
                synthesis=False if no_synthesis else None,
                memory=open_memory(config, root=Path.cwd(), enabled=not no_memory),
            )
        ),
        renderer,
        observers,
    )
    observers.finish()
    _print_usage(observers, quiet=quiet or as_json)
    if result.source is VerdictSource.NONE:
        raise typer.Exit(1)


@app.command()
def doctor(
    live: Annotated[
        bool,
        typer.Option("--live", help="Sağlayıcılara küçük gerçek çağrı yap (kota harcar)."),
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Betikler için JSON çıktı.")] = False,
) -> None:
    """Kurulumu denetle: ne eksik, neden önemli, ne yapmalı.

    Çıkış kodu 1 YALNIZ kurulum kullanılamazsa (agent rolü çalışmıyor); PATH ya da yazılamayan
    dizin gibi diğer sorunlar için betikler `--json` çıktısındaki `ok` alanına bakmalı.
    """
    from .doctor import diagnose, to_dict

    rapor = diagnose(live=live)
    if as_json:
        console.print_json(data=to_dict(rapor))
    else:
        _print_doctor(rapor)
    # Çıkış kodu betikler içindir: kurulum kullanılamaz durumdaysa sıfır dışı.
    raise typer.Exit(0 if rapor.readiness.state is not Readiness.NOT_READY else 1)


def _print_doctor(report: DoctorReport) -> None:
    """Tanıyı oku-yazılabilir biçimde bas. Sır içermez."""
    console.print()
    for check in report.checks:
        isaret = "·" if check.ok is None else (theme.ICON_OK if check.ok else theme.ICON_ERROR)
        renk = theme.DIM if check.ok is None else (theme.OK if check.ok else theme.ERROR)
        console.print(f"[{renk}]{isaret}[/{renk}] {check.name:<28} {escape(check.value)}")
        if check.remedy:
            console.print(f"  [{theme.DIM}]→ {escape(check.remedy)}[/{theme.DIM}]")
    console.print()
    durum = report.readiness.state
    renk = {Readiness.READY: theme.OK, Readiness.PARTIALLY_READY: theme.WARN}.get(
        durum, theme.ERROR
    )
    console.print(f"[bold {renk}]{messages.DOCTOR_STATE[durum.value]}[/bold {renk}]")
    for sebep in report.readiness.reasons:
        console.print(f"  [{theme.DIM}]{escape(sebep)}[/{theme.DIM}]")


@app.command()
def update() -> None:
    """Fusion'ı nasıl güncelleyeceğini göster."""
    from .maintenance import current_method, update_instructions

    console.print(messages.MAINT_METHOD.format(method=current_method().value))
    console.print()
    console.print(f"  {update_instructions()}")
    console.print()


@app.command()
def uninstall(
    purge: Annotated[
        bool,
        typer.Option(
            "--purge",
            help="Yapılandırma, anahtarlar ve belleği de sil (varsayılan: KORUNUR).",
        ),
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="--purge için onay sorma (betikler).")
    ] = False,
) -> None:
    """Fusion'ı nasıl kaldıracağını göster; istenirse kullanıcı verisini sil."""
    from .maintenance import (
        current_method,
        purge_targets,
        purge_user_data_report,
        uninstall_instructions,
    )

    console.print(messages.MAINT_METHOD.format(method=current_method().value))
    console.print()
    console.print(f"  {uninstall_instructions()}")
    console.print()
    if not purge:
        console.print(f"[{theme.DIM}]{messages.MAINT_DATA_KEPT}[/{theme.DIM}]")
        return
    hedefler = purge_targets()
    if not hedefler:
        console.print(f"[{theme.DIM}]{messages.MAINT_NOTHING_TO_PURGE}[/{theme.DIM}]")
        return
    # Kalıcı silme onaysız yapılmaz: Ölçüldü (30 Ekim) `--purge` tek başına anahtarları
    # ve belleği soru sormadan `rmtree` ediyordu (L1-10).
    for yol in hedefler:
        console.print(f"  {escape(str(yol))}")
    if not yes and not typer.confirm(messages.MAINT_PURGE_CONFIRM, default=False):
        console.print(f"[{theme.DIM}]{messages.MAINT_PURGE_ABORTED}[/{theme.DIM}]")
        raise typer.Exit(1)
    sonuc = purge_user_data_report(dry_run=False)
    for yol in sonuc.removed:
        console.print(
            f"[{theme.OK}]{theme.ICON_OK}[/{theme.OK}] {messages.MAINT_REMOVED} {escape(str(yol))}"
        )
    for yol, sebep in sonuc.failed:
        hata = messages.MAINT_PURGE_FAILED.format(path=yol, reason=sebep)
        console.print(f"[{theme.ERROR}]{theme.ICON_ERROR} {escape(hata)}[/{theme.ERROR}]")
    if sonuc.failed:
        raise typer.Exit(1)


@app.command()
def agent(
    task: str = typer.Argument(..., help="Agent'a verilecek görev."),
    mode: str = typer.Option(
        "auto",
        "--mode",
        "-m",
        help="Onay modu: auto (yalnız riskli işlemde sorar) | edits (düzenlemeler "
        "sorulmaz) | security/manual (her değişikliği sor) | plan (yalnız planla) | "
        "bypass (hiçbir şey sorma)",
    ),
    no_memory: bool = typer.Option(
        False, "--no-memory", help="Belleği kullanma ve yazma (ders çıkarımı kapalı)."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Olayları satır satır JSON olarak yaz (betikler için)."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="İlerleme satırlarını gizle."),
    add_dir: Annotated[
        list[Path] | None,
        typer.Option(
            "--add-dir",
            help="Proje kökünün YANINDA erişime açılacak dizin. Birden çok kez verilebilir.",
        ),
    ] = None,
    worktree: Annotated[
        str,
        typer.Option(
            "--worktree",
            "-w",
            help="Görevi izole git çalışma ağacında koş (.fusion/worktrees/<ad>); ağaç korunur.",
        ),
    ] = "",
) -> None:
    """Görevi araçlarla çalıştır: dosya oku/yaz, komut çalıştır, web'de ara."""
    if not task.strip():
        raise typer.BadParameter(messages.RUN_EMPTY_TASK)
    approval = _parse_mode(mode)

    config = load_config()
    try:
        root, tree = worktrees.resolve_launch_root(Path.cwd(), worktree)
    except FusionError as error:
        error_console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
        raise typer.Exit(1) from None
    if tree is not None and worktree.strip() and not as_json:
        _print_worktree_notice(tree)
    renderer = ConsoleRenderer(console, show_progress=not quiet)
    observers = build_observers(
        task, renderer=renderer, as_json=as_json, trace_dir=config.memory_dir / "traces"
    )
    # Tek atışta oturum yoktur: `enter_worktree` isteği tur sonunda köke dönüşmez, yalnız
    # açılan ağaç bildirilir (ağaç korunur; sonraki iş `fusion -w <ad>` ile oradan sürer).
    switch = WorktreeSwitch()

    # `k` (kalıcı izin) burada da kural YAZAR: hafızaya yazıcı bağlanır, bildirim tur sonunda
    # basılır (P-003; ölçüldü 31 Ekim: bağlanmıyordu, `k` yalnız oturum içi hatırlıyordu).
    approval_memory = attach_rule_writer(ApprovalMemory(), root)
    outcome = _run_observed(
        with_web_cleanup(
            run_agent_task(
                task,
                config,
                sinks=observers.sinks,
                prompter_factory=lambda flush: ConsolePrompter(
                    console,
                    ToolContext(
                        root=root,
                        extra_roots=tuple(add_dir or ()),
                        restrict_to_root=config.runtime.restrict_to_root,
                    ),
                    flush=flush,
                ),
                mode=approval,
                root=root,
                home=Path.home(),
                memory=open_memory(config, root=root, enabled=not no_memory),
                extra_roots=tuple(add_dir or ()),
                approval_memory=approval_memory,
                worktree_switch=switch,
            )
        ),
        renderer,
        observers,
    )
    observers.finish()
    print_rule_notices(console, approval_memory)
    opened, _exit_requested = switch.take()
    if opened is not None and not as_json:
        _print_worktree_notice(opened)
    _print_usage(observers, quiet=quiet or as_json)
    # Çıkış kodu `outcome.ok`a bakar (paperclip ile aynı kural): Ölçüldü (30 Ekim) yalnız
    # boş metin 1 yapıyordu; hata mesajı/bütçe durdurması/hız sınırı dolu metinle 0 dönüyor,
    # betikler başarısızlığı yakalayamıyordu (L1-46).
    if not outcome.final_text.strip() or not outcome.ok:
        raise typer.Exit(1)


@app.command()
def init(
    fmt: str = typer.Option(
        "agents", "--format", "-f", help="Üretilecek dosya: agents (AGENTS.md) | claude (CLAUDE.md)"
    ),
    mode: str = typer.Option("edits", "--mode", "-m", help="Onay modu (varsayılan: edits)."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="İlerleme satırlarını gizle."),
) -> None:
    """Depoyu inceleyip kök talimat dosyasını (AGENTS.md / CLAUDE.md) üret — /init ile aynı."""
    from ..engines.agent.instruction_audit import init_task

    config = load_config()
    root = Path.cwd()
    task = init_task(root, Path.home(), fmt=fmt)
    renderer = ConsoleRenderer(console, show_progress=not quiet)
    observers = build_observers(
        task, renderer=renderer, as_json=False, trace_dir=config.memory_dir / "traces"
    )
    outcome = _run_observed(
        with_web_cleanup(
            run_agent_task(
                task,
                config,
                sinks=observers.sinks,
                prompter_factory=lambda flush: ConsolePrompter(
                    console,
                    ToolContext(root=root, restrict_to_root=config.runtime.restrict_to_root),
                    flush=flush,
                ),
                mode=_parse_mode(mode),
                root=root,
                home=Path.home(),
                memory=open_memory(config, root=root),
            )
        ),
        renderer,
        observers,
    )
    observers.finish()
    if not outcome.ok:
        raise typer.Exit(1)


def _run_observed(
    coro: Coroutine[Any, Any, T], renderer: ConsoleRenderer, observers: Observers
) -> T:
    """Koşuyu çalıştır; hata/Ctrl-C ile KESİLİRSE göstergeyi ve izi yine kapat.

    `TurnFinished` yayınlanmadan çıkış `Live` göstergesini açık, iz dosyasını kapanmamış
    bırakıyordu (L1-28). Normal bitişte `abort` etkisizdir; istisna aynen yeniden fırlatılır.
    """
    try:
        return asyncio.run(coro)
    except BaseException:
        renderer.abort()
        observers.finish()
        raise


def _parse_mode(raw: str) -> ApprovalMode:
    try:
        return parse_mode(raw)
    except ValueError:
        valid = ", ".join(item.value for item in ApprovalMode)
        raise typer.BadParameter(messages.RUN_UNKNOWN_MODE.format(given=raw, valid=valid)) from None


@app.command()
def models(
    fetch: bool = typer.Option(
        False, "--fetch", help="Sağlayıcıların CANLI kataloğundan kullanılabilir modelleri listele."
    ),
) -> None:
    """Yapılandırılmış modelleri, `--fetch` ile canlı katalogları göster."""
    if not fetch:
        _print_configured_models(load_config())
        return
    load_config()  # .env yüklenir; NIM anahtarı katalog için gerekir
    _print_catalog()


@app.command()
def feedback(
    task_type: str = typer.Argument(..., help="Görev tipi (general | code | reasoning | agent)."),
    model: str = typer.Argument(..., help="Geri bildirim verilecek aday adı."),
    verdict: str = typer.Argument(..., help="good | bad | revise"),
) -> None:
    """Bir modelin son sonucuna geri bildirim ver; bellek buna göre öğrenir."""
    memory_commands.feedback(task_type, model, verdict)


@app.command()
def serve(
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Dinlenecek yerel adres. Varsayılan yalnızca bu bilgisayar."
    ),
    port: int = typer.Option(8787, "--port", "-p", help="Dinlenecek port."),
    compact_context: bool = typer.Option(
        False,
        "--compact-context",
        help="Bağlam bütçesini aşan uzun geçmişi özetle (geçmişi kendisi yönetmeyen "
        "istemciler için; Fusion Kits açar).",
    ),
    token: str = typer.Option(
        "",
        "--token",
        envvar="FUSION_GATEWAY_TOKEN",
        help="Bu bilgisayar dışından gelen isteklerin taşıması gereken belirteç "
        "(Authorization: Bearer). 127.0.0.1 dışında dinlemek için zorunlu.",
    ),
) -> None:
    """Yerel gateway'i çalıştır: OpenAI-uyumlu /v1 uç noktası, tüm sağlayıcılar arkada.

    Böylece bu bilgisayardaki her araç (Cursor, Cline, OpenAI-uyumlu her CLI) Fusion'a
    bağlanır — hiçbir uygulama bozulmadan/rootlanmadan. Uzak sunucu değildir; yalnız
    yerelde çalışır. Model olarak profil adı (auto/low/medium/high/max) ya da ham model
    kimliği verilebilir; fallback ve sağlık otomatik devrededir.
    """
    from ..gateway.server import serve as run_gateway

    config = load_config()
    console.print(
        f"[bold]Fusion gateway[/bold] → http://{host}:{port}/v1\n"
        f"[dim]panel: [/dim]http://{host}:{port}/dashboard   "
        f"[dim](model: auto/low/medium/high/max ya da ham kimlik · Ctrl-C ile durdur)[/dim]"
    )
    try:
        run_gateway(
            config,
            host=host,
            port=port,
            compact_context=compact_context,
            access_token=token or None,
        )
    except FusionError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error


@app.command()
def trust(
    path: Annotated[
        Path, typer.Argument(help="Güvenilecek proje kökü (varsayılan: bulunduğun dizin).")
    ] = Path(),
) -> None:
    """Projenin config.yaml, .fusion/tools ve .claude/settings.local.json dosyalarına güven.

    Güvenilmeyen projede bu dosyalar MCP süreci, doğrulama komutu, araç ya da
    onaysız kabuk komutu (izin listesi) çalıştıramaz. Dosyalar sonradan değişirse
    güven kendiliğinden düşer.
    """
    from ..config import trust as project_trust

    root = path.resolve()
    if not root.is_dir():
        console.print(f"[red]Dizin bulunamadı: {root}[/red]")
        raise typer.Exit(code=1)
    project_trust.trust_project(root)
    console.print(f"[green]Güvenildi:[/green] {root}")


@app.command()
def permissions(
    action: Annotated[
        str, typer.Argument(help="list | add | remove (Claude Code /permissions eşdeğeri).")
    ] = "list",
    decision: Annotated[str, typer.Argument(help="allow | ask | deny")] = "",
    pattern: Annotated[
        list[str] | None,
        typer.Argument(help="Kalıp: Bash(npm test *), Edit(/src/**), WebFetch(domain:x)…"),
    ] = None,
    user: Annotated[
        bool,
        typer.Option("--user", help="Projeye değil kullanıcı dosyasına (permissions.json) yaz."),
    ] = False,
    path: Annotated[
        Path, typer.Option("--path", help="Proje kökü (varsayılan: bulunduğun dizin).")
    ] = Path(),
) -> None:
    """İzin kurallarını (allow/ask/deny) listele, ekle, sil (P-003).

    Kurallar Claude Code ile aynı dosyalarda durur: projenin `.claude/settings.local.json`'ı
    (güvenilen projede) ya da kullanıcının `permissions.json`'ı. Örnek:
    `fusion permissions add allow "Bash(npm test *)"`.
    """
    from ..config import permission_admin
    from ..config.loader import load_config
    from ..ui import messages

    root = path.resolve()
    if action in ("list", "liste"):
        rows = permission_admin.rule_rows(root)
        if not rows:
            console.print(messages.PERMISSIONS_EMPTY)
        for row in rows:
            console.print(escape(f"· {row.pattern}  [{row.decision}]  ({row.source})"))
        config = load_config()
        console.print(
            f"kök dışı: okuma {'KAPALI' if config.runtime.block_reads_outside_root else 'açık'} · "
            f"yazma {'KAPALI' if config.runtime.block_writes_outside_root else 'onayla'}"
        )
        return
    if action not in ("add", "remove") or not decision or not pattern:
        console.print(f"[red]{escape(messages.PERMISSIONS_USAGE)}[/red]")
        raise typer.Exit(code=2)
    try:
        karar = permission_admin.parse_decision(decision)
    except ValueError:
        console.print(
            f"[red]{escape(messages.PERMISSIONS_BAD_DECISION.format(given=decision))}[/red]"
        )
        raise typer.Exit(code=2) from None
    kalip = " ".join(pattern)
    try:
        rule = permission_admin.parse_pattern(kalip, karar)
    except ValueError:
        console.print(f"[red]{escape(messages.PERMISSIONS_BAD_PATTERN.format(given=kalip))}[/red]")
        raise typer.Exit(code=2) from None
    try:
        if action == "add":
            change = permission_admin.add_permission_rule(root, rule, user_level=user)
            text = (
                permission_admin.added_message(change, karar)
                if change.changed
                else messages.PERMISSIONS_EXISTS.format(rule=change.pattern, decision=karar.value)
            )
        else:
            removed = permission_admin.remove_permission_rule(root, rule)
            text = (
                messages.PERMISSIONS_REMOVED.format(
                    rule=removed.pattern, decision=karar.value, path=removed.path
                )
                if removed is not None
                else messages.PERMISSIONS_NOT_FOUND.format(rule=rule.pattern, decision=karar.value)
            )
    except FusionError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error
    console.print(escape(text))


@app.command("adopt-data")
def adopt_data(
    account: Annotated[
        str,
        typer.Argument(
            help="Eski ortak veriyi alacak hesabın kullanıcı adı, e-postası ya da kimliği."
        ),
    ] = "",
) -> None:
    """Hesapsız düzenin ortak verisini (bellek, sırlar, tarayıcı oturumları) TEK hesaba bağla.

    Hesap verilmezse yalnız envanteri gösterir. Veri kopyalanır, eski kök korunur;
    diğer hesaplar boş başlar. Ardından FUSION_WORKSPACE_ISOLATION=1 ile her hesap
    kendi verisini kullanır.
    """
    from ..accounts import SqliteAccountStore
    from ..accounts.data_migration import MigrationError, migrate_legacy_data, migration_inventory

    if not account:
        inventory = migration_inventory()
        table = Table("girdi", "tür", "boyut (KB)")
        for entry in inventory.entries:
            kind = "klasör" if entry.is_dir else "dosya"
            table.add_row(entry.name, kind, str(max(entry.size_bytes, 0) // 1024))
        console.print(table)
        owner = inventory.owner or "seçilmedi"
        console.print(f"Kaynak: {inventory.source} · sahip: {owner}")
        return
    wanted = account.strip().casefold()
    match = next(
        (
            item
            for item in SqliteAccountStore().list_accounts()
            if wanted
            in {item.account_id.casefold(), item.username.casefold(), item.email.casefold()}
        ),
        None,
    )
    if match is None:
        console.print(f"[red]Hesap bulunamadı: {account}[/red]")
        raise typer.Exit(code=1)
    try:
        result = migrate_legacy_data(match.account_id)
    except (MigrationError, OSError) as error:
        console.print(
            f"[red]Taşıma tamamlanmadı: {error}[/red] Eski veri yerinde ve okunur durumda."
        )
        raise typer.Exit(code=1) from error
    if result.already_done:
        console.print(f"Eski veri zaten {match.username} hesabına bağlı: {result.target}")
        return
    console.print(
        f"[green]{match.username} hesabına kopyalandı:[/green] {', '.join(result.copied) or '-'}"
    )
    console.print("Etkinleştirmek için: FUSION_WORKSPACE_ISOLATION=1")


@app.command()
def mcp(
    write: bool = typer.Option(
        False, "--write", help="Değiştirici araçları da aç (dikkat: dışarıya yazma verir)."
    ),
) -> None:
    """Fusion araçlarını bir MCP sunucusu olarak aç (stdio).

    MCP destekleyen araçlar (Claude masaüstü, Cursor, Cline…) buna bağlanıp Fusion'ın
    araçlarını (kod arama, dosya okuma…) kullanabilir. Varsayılan yalnızca salt-okunur.
    """
    # DİKKAT: stdout MCP protokolüne aittir; buraya hiçbir şey BASILMAZ.
    try:
        from ..mcp_bridge.server import run_stdio
    except ImportError:
        typer.echo(messages.MCP_MISSING_DEP, err=True)
        raise typer.Exit(code=1) from None
    asyncio.run(run_stdio(Path.cwd(), expose_mutating=write))


@app.command(name="chrome-host", hidden=True)
def chrome_host() -> None:
    """Chrome eklentisinin yerel mesajlaşma sunucusu (Chrome başlatır, elle değil)."""
    from ..appserver.chrome_host import main as host_main

    host_main()


@app.command(name="chrome-kur")
def chrome_kur() -> None:
    """Fusion Browser eklentisini Chrome'a kurmaya hazırla (tek onaylı akış)."""
    from ..appserver.chrome_install import begin_install

    sonuc = begin_install()
    if not sonuc["ok"]:
        typer.echo(sonuc["metin"], err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Eklenti klasörü (panoya kopyalandı): {sonuc['yol']}")
    for sira, adim in enumerate(sonuc["adimlar"], start=1):
        typer.echo(f"{sira}. {adim}")


@app.command(name="web-login")
def web_login(provider: str, account: str = "main") -> None:
    """Web sağlayıcısı için görünür giriş tarayıcısını aç.

    Paketlenmiş ikilide `python -m fusion_cli.providers.web_login` ÇALIŞMAZ:
    `sys.executable` Fusion ikilisidir ve `-m` bayrağını tanımaz. Kaynak
    kurulumda da kabuğun varsayılan `python`'u venv değilse modülü bulamaz.
    Bu komut iki kurulumda da aynı pencereyi açar.

    ARTIK GİZLİ DEĞİL: oturum insan doğrulaması istediğinde kullanıcıya
    gösterilen çözüm adımı bu komutu söylüyor (`providers/web_browser.py::
    _cozum_adimlari`). Hata metninin önerdiği ama `--help`'te görünmeyen bir
    komut, adını hatırlamayan kullanıcı için çıkışsız bir yol demekti.
    """
    from ..providers.web_browser import open_login_browser

    asyncio.run(open_login_browser(provider, account))


@app.command(name="ema-say", hidden=True)
def ema_say(output: str) -> None:
    """Standart girdideki metni EMA Lightning ile seslendirip WAV'a yaz.

    Paketlenmiş ikilide ses motoru süreç dışından bu alt komutla sınanabilir.
    """
    from ..appserver.ema_synthesis import synthesize_ema
    from ..appserver.voice import load_settings

    synthesize_ema(sys.stdin.read(), Path(output), load_settings()["hiz"])


@app.command(name="runtime-health", hidden=True)
def runtime_health(as_json: bool = typer.Option(False, "--json")) -> None:
    """Paketli masaüstü çalışma zamanının bütünlüğünü doğrula."""
    import json

    from ..runtime_health import collect_runtime_health

    report = collect_runtime_health()
    if as_json:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        template = (
            messages.RUNTIME_HEALTH_OK if report.resources_ok else messages.RUNTIME_HEALTH_BROKEN
        )
        typer.echo(template.format(version=report.version))
    if not report.resources_ok:
        raise typer.Exit(1)


@app.command(name="app")
def app_protocol(ctx: typer.Context) -> None:
    """Masaüstü uygulaması için stdio protokolünü konuş.

    Uygulama bu süreci kendisi doğurur ve stdin/stdout üzerinden satır satır
    JSON konuşur. Doğrudan elle çalıştırmak için değildir.
    """
    from ..accounts import activate_account, remembered_account
    from ..appserver.server import run_stdio

    # Etkin hesap YAPILANDIRMA OKUNMADAN ÖNCE seçilmelidir: `config.yaml` hesaba
    # özel bir dizinden gelir ve oturum nesnesi kurulurken zaten yükleniyor.
    # Hatırlanan hesap yoksa hesapsız (eski) düzen geçerli kalır.
    hesap = remembered_account()
    if hesap:
        activate_account(hesap)

    host = ctx.obj if isinstance(ctx.obj, AppHostDependencies) else None
    if host is not None and (
        host.remotion_transport is not None
        or host.remotion_browser is not None
        or host.require_remotion_kit
    ):
        asyncio.run(
            run_stdio(
                Path.cwd(),
                Path.home(),
                remotion_transport=host.remotion_transport,
                remotion_browser=host.remotion_browser,
                require_remotion_kit=host.require_remotion_kit,
            )
        )
    else:
        asyncio.run(run_stdio(Path.cwd(), Path.home()))


@app.command(name="mcp-tools")
def mcp_tools() -> None:
    """Yapılandırılmış dış MCP sunucularının araçlarını listele (bağlanır ve keşfeder)."""
    config = load_config()
    if not config.mcp_servers:
        console.print(messages.MCP_NO_SERVERS)
        return
    try:
        from ..mcp_bridge.client import McpClient
    except ImportError:
        console.print(f"[red]{messages.MCP_MISSING_DEP}[/red]")
        raise typer.Exit(code=1) from None

    async def _run() -> None:
        async with McpClient(config.mcp_servers) as client:
            for server in config.mcp_servers:
                tools = await client.list_tools(server.name)
                console.print(f"[bold]{escape(server.name)}[/bold] — {len(tools)} araç:")
                for tool in tools:
                    console.print(
                        f"  [{theme.ACCENT}]{escape(tool.name)}[/{theme.ACCENT}] — "
                        f"{escape(tool.description or '')}"
                    )

    try:
        asyncio.run(asyncio.wait_for(_run(), timeout=MCP_TOOLS_TIMEOUT_S))
    except FusionError:
        raise
    except TimeoutError as error:
        # Bağlanamayan sunucu komutu sonsuza dek bekletmesin ve çıplak traceback vermesin
        # (L1-26).
        raise FusionError(messages.MCP_TOOLS_TIMEOUT.format(seconds=MCP_TOOLS_TIMEOUT_S)) from error
    except Exception as error:
        raise FusionError(messages.MCP_CONNECT_FAILED.format(error=error)) from error


@app.command(name="mcp-add")
def mcp_add(
    name: Annotated[str, typer.Argument(help="Sunucuya vereceğin kısa ad (ör. github).")],
    command: Annotated[str, typer.Argument(help="Çalıştırılacak komut (ör. npx).")],
    args: Annotated[
        list[str] | None,
        typer.Argument(help="Komuta verilecek argümanlar. `-` ile başlıyorsa önce -- koy."),
    ] = None,
) -> None:
    """Dış bir MCP sunucusunu `config.yaml`'a ekle; kullanıcı config'i elle düzenlemez.

    Agent bu komutu KENDİ dosya araçlarıyla DEĞİL, yalnızca bu CLI komutunu shell'de
    çalıştırarak tetikler — `config.yaml` agent'ın genel yazma sınırının dışındadır
    (güvenlik sınırı, docs/WEB_PROVIDERS.md ile aynı ilke).

    Örnek: `fusion mcp-add github npx -- -y @modelcontextprotocol/server-github`
    (argümanlar `-` ile başlıyorsa Typer'ın seçenek sanmaması için `--` şart).
    """
    from ..config.models import McpServerConfig
    from ..config.writer import write_mcp_servers

    config = load_config()
    kalanlar = tuple(server for server in config.mcp_servers if server.name != name)
    yeniden_yazildi = len(kalanlar) != len(config.mcp_servers)
    yeni = McpServerConfig(name=name, command=command, args=tuple(args or ()))
    guncellenmis = replace(config, mcp_servers=(*kalanlar, yeni))

    path = write_mcp_servers(guncellenmis)
    template = messages.MCP_REPLACED if yeniden_yazildi else messages.MCP_ADDED
    console.print(template.format(name=name))
    console.print(f"[{theme.DIM}]{path}[/{theme.DIM}]")


@app.command()
def setup() -> None:
    """İlk kurulum: kullanıcı dizinine config.yaml ve .env şablonu bırak."""
    run_setup(console)


@app.command()
def trace(
    run_id: str = typer.Argument("", help="Koşu kimliği; verilmezse sonuncusu."),
    liste: bool = typer.Option(False, "--list", "-l", help="Kayıtlı koşuları listele."),
) -> None:
    """Bir koşunun teşhis özetini göster: hangi kayıp sınıfı, nerede duraklandı."""
    from ..observability.trace_store import TraceStore
    from .trace_command import list_runs, render_trace

    store = TraceStore(load_config().memory_dir / "traces")
    if liste:
        list_runs(store)
        return
    render_trace(store, run_id or None)


@app.command()
def stats() -> None:
    """Model performans tablosu (`fusion memory stats` ile aynı)."""
    memory_commands.show_stats()


@app.command()
def version() -> None:
    """Sürümü yazdır."""
    console.print(messages.VERSION.format(version=__version__))


@config_app.command("show")
def config_show() -> None:
    """Birleştirilmiş yapılandırmayı göster (varsayılanlar + kullanıcı dosyası)."""
    config = load_config()
    _print_config(config)


@config_app.command("teacherless")
def config_teacherless(
    enabled: bool = typer.Argument(..., help="true|false — öğretmensiz kipi aç/kapat"),
) -> None:
    """Öğretmensiz çalış: `ask_teacher` aracı modele hiç sunulmaz."""
    from ..config.writer import write_runtime_flag

    config = load_config()
    write_runtime_flag(config, "teacherless", enabled)
    console.print(messages.CONFIG_TEACHERLESS_SET.format(state=_acik_kapali(enabled)))


@config_app.command("teacher-lesson-sync")
def config_teacher_lesson_sync(
    enabled: bool = typer.Argument(..., help="true|false — öğretmen derslerini ders belleğine yaz"),
) -> None:
    """Öğretmen cevaplarından çıkan dersler ders belleğine (`recall_lessons`) de yazılsın mı?"""
    from ..config.writer import write_runtime_flag

    config = load_config()
    write_runtime_flag(config, "teacher_lesson_sync", enabled)
    console.print(messages.CONFIG_TEACHER_LESSON_SYNC_SET.format(state=_acik_kapali(enabled)))


def _acik_kapali(enabled: bool) -> str:
    return "açık" if enabled else "kapalı"


def _print_config(config: Config) -> None:
    source = (
        messages.CONFIG_SOURCE_FILE.format(path=config.source)
        if config.source is not None
        else messages.CONFIG_SOURCE_DEFAULTS
    )
    console.print(f"[{theme.DIM}]{source}[/{theme.DIM}]\n")

    console.print(f"[bold]{messages.CONFIG_HEADING_CANDIDATES}[/bold]")
    for candidate in config.candidates:
        _print_spec(candidate)
    console.print(f"\n[bold]{messages.CONFIG_HEADING_JUDGE}[/bold]")
    _print_spec(config.judge)
    console.print(f"\n[bold]{messages.CONFIG_HEADING_AGENT}[/bold]")
    _print_spec(config.agent)

    console.print(f"\n[bold]{messages.CONFIG_HEADING_RUNTIME}[/bold]")
    for field in fields(config.runtime):
        value = getattr(config.runtime, field.name)
        console.print(f"  [{theme.DIM}]{field.name}:[/{theme.DIM}] {value}")


def _print_spec(spec: ModelSpec) -> None:
    tags = f" [{theme.DIM}]({escape(', '.join(spec.tags))})[/{theme.DIM}]" if spec.tags else ""
    console.print(
        f"  {escape(spec.name)}: [{theme.ACCENT}]{escape(spec.model)}[/{theme.ACCENT}]{tags}"
    )
    if spec.fallback:
        for fallback in spec.fallback:
            console.print(f"    [{theme.DIM}]yedek: {escape(fallback)}[/{theme.DIM}]")
    else:
        console.print(f"    [{theme.DIM}]{messages.CONFIG_FALLBACK_NONE}[/{theme.DIM}]")


def _print_usage(observers: Observers, *, quiet: bool) -> None:
    """Tur sonunda token/maliyet özetini ve izleme durumunu göster."""
    if quiet or not observers.cost.calls:
        return
    console.print(f"[{theme.DIM}]{cost_summary(observers.cost)}[/{theme.DIM}]")


def _print_configured_models(config: Config) -> None:
    table = Table(title=messages.CONFIG_HEADING_CANDIDATES)
    table.add_column("Rol", style="bold")
    table.add_column("Ad", style=theme.ACCENT)
    table.add_column("Model", style=theme.DIM)
    for candidate in config.candidates:
        table.add_row("aday", escape(candidate.name), escape(candidate.model))
    table.add_row("hakem", escape(config.judge.name), escape(config.judge.model))
    table.add_row("agent", escape(config.agent.name), escape(config.agent.model))
    for session in config.web_sessions:
        if session.enabled:
            table.add_row(
                "web", escape(f"{session.provider}/{session.account}"), escape(session.model)
            )
    console.print(table)


def _print_catalog() -> None:
    """Canlı katalogları listele. Ağ yoksa boş liste döner, komut çökmez."""
    from ..providers.catalog import fetch_nim, fetch_openrouter_free

    for title, entries in (
        (messages.CATALOG_OPENROUTER, fetch_openrouter_free()),
        (messages.CATALOG_NIM, fetch_nim()),
    ):
        if not entries:
            console.print(f"[{theme.DIM}]{title}: {messages.CATALOG_EMPTY}[/{theme.DIM}]")
            continue
        console.print(f"\n[bold]{title}[/bold] [{theme.DIM}]({len(entries)})[/{theme.DIM}]")
        for entry in entries:
            suffix = (
                f"  [{theme.DIM}]{entry.context_length:,} token[/{theme.DIM}]"
                if entry.context_length
                else ""
            )
            console.print(f"  [{theme.ACCENT}]{escape(entry.model_id)}[/{theme.ACCENT}]{suffix}")


def configure_file_logging() -> None:
    """Paket uyarılarını kullanıcı veri dizinindeki `logs/fusion.log`'a yönlendir.

    Ölçüldü (30 Ekim, gerçek kullanım denemesi): `fusion_cli` günlüğüne işleyici bağlı
    olmadığı için Python'un son çare işleyicisi `logger.warning` satırlarını ham hâliyle
    terminale basıyordu ("model secenegi tiklanamadi: … Locator.click: Timeout …").
    Kullanıcıya görünen bilgi olaylarla gelir; ayrıntı dosyaya gider. Dosya açılamazsa
    sessiz bir işleyici bağlanır: uyarı yine terminale sızmaz. Tekrar çağrı çoğaltmaz.
    """
    kok = logging.getLogger("fusion_cli")
    if any(getattr(handler, "_fusion_dosya", False) for handler in kok.handlers):
        return
    handler: logging.Handler
    try:
        klasor = user_data_dir() / "logs"
        klasor.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            klasor / "fusion.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    except OSError:
        handler = logging.NullHandler()
    handler.setLevel(logging.WARNING)
    setattr(handler, "_fusion_dosya", True)  # noqa: B010 - işaret, işleyici sınıfında yok
    kok.addHandler(handler)


def main(*, host_dependencies: AppHostDependencies | None = None) -> None:
    """Konsol giriş noktası. Beklenen hataları kullanıcıya anlaşılır biçimde gösterir."""
    configure_file_logging()
    try:
        app(obj=host_dependencies)
    except FusionError as exc:
        error_console.print(
            f"[{theme.ERROR}]{theme.ICON_ERROR} {messages.ERROR_PREFIX}[/{theme.ERROR}] "
            f"{escape(str(exc))}"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        error_console.print(f"[{theme.WARN}]{messages.ERROR_INTERRUPTED}[/{theme.WARN}]")
        sys.exit(130)


if __name__ == "__main__":  # `python -m fusion_cli.cli.app`
    # Modül olarak çalıştırma konsol girişiyle AYNI yolu izlemeli. Bu blok yokken
    # `python -m fusion_cli.cli.app` modülü yalnız içe aktarıyor, hiçbir komut
    # çalıştırmadan sessizce 0 ile çıkıyordu — kurulum sarmalayıcıları bu yolu
    # kullandığı için komut hiçbir şey yapmıyormuş gibi görünüyordu.
    main()

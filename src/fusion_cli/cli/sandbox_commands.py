"""`fusion sandbox` — kabuk sandbox'ı durumu, ayarları ve deneme çalıştırması (P-010).

    fusion sandbox durum                 platform, kurulabilirlik, kurallar
    fusion sandbox ac | kapat            runtime.shell_sandbox
    fusion sandbox ag allowlist          ağ kipi (open | allowlist)
    fusion sandbox izin github.com       izinli alan adı (engelle / kaldir aynı biçim)
    fusion sandbox oto on                auto_allow (zorunlu, disari, sir, localhost aynı biçim)
    fusion sandbox calistir -- curl …    komutu ŞU ANKİ politikayla sandbox içinde dene

`calistir`, Codex'in `codex sandbox` komutu gibi: kip kapalı olsa da komut sandbox içinde
koşar; çıkış, engellenen yazma/okuma/alan adı notlarıyla birlikte basılır.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from ..config.loader import load_config
from ..config.sandbox_admin import apply_sandbox_action, sandbox_status
from ..config.sandbox_config import fusion_secret_paths, sandbox_policy
from ..core.errors import ConfigError
from ..core.shell_sandbox import SHELL_SANDBOX_WRITE_ROOT
from ..core.tools import ToolContext
from ..tools.shell import run_shell
from .sandbox_view import format_change, format_status

app = typer.Typer(no_args_is_help=True, help="Kabuk sandbox'ı: durum, ayarlar, deneme.")
console = Console()


def _act(action: str, value: str = "") -> None:
    try:
        change = apply_sandbox_action(load_config(), action, value, root=Path.cwd())
    except ConfigError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(1) from error
    console.print(escape(format_change(change)))


@app.command("durum")
def status() -> None:
    """Sandbox durumu ve etkin kurallar."""
    console.print(escape(format_status(sandbox_status(load_config(), Path.cwd()))))


@app.command("ac")
def enable() -> None:
    """Sandbox'ı aç (runtime.shell_sandbox=write_root)."""
    _act("ac")


@app.command("kapat")
def disable() -> None:
    """Sandbox'ı kapat (runtime.shell_sandbox=off)."""
    _act("kapat")


@app.command("ag")
def network(mode: Annotated[str, typer.Argument(help="open | allowlist")]) -> None:
    """Ağ kipi: open (kısıtsız) ya da allowlist (yalnız izinli alan adları)."""
    _act("ag", mode)


@app.command("izin")
def allow(domain: Annotated[str, typer.Argument(help="ör. github.com, *.npmjs.org")]) -> None:
    """İzinli alan adı ekle (ağ kipi allowlist'e geçer)."""
    _act("izin", domain)


@app.command("engelle")
def deny(domain: Annotated[str, typer.Argument(help="alan adı")]) -> None:
    """Yasak alan adı ekle (izin listesinden üstündür)."""
    _act("engelle", domain)


@app.command("kaldir")
def remove(domain: Annotated[str, typer.Argument(help="alan adı")]) -> None:
    """Alan adını iki listeden de çıkar."""
    _act("kaldir", domain)


_OnOff = Annotated[str, typer.Argument(help="on | off")]


@app.command("oto")
def auto_allow(value: _OnOff) -> None:
    """Sandbox içindeki komutları sormadan çalıştır (sandbox.auto_allow; ağ allowlist'te)."""
    _act("oto", value)


@app.command("zorunlu")
def strict(value: _OnOff) -> None:
    """Sandbox kurulamazsa komutu çalıştırma (sandbox.fail_if_unavailable)."""
    _act("zorunlu", value)


@app.command("disari")
def outside(value: _OnOff) -> None:
    """Modelin sandbox dışı isteğine (her seferinde onaylı) izin ver (sandbox.allow_unsandboxed)."""
    _act("disari", value)


@app.command("sir")
def secrets(value: _OnOff) -> None:
    """Sır görünümlü ortam değişkenlerini sandbox'ta gizle (sandbox.hide_secret_env)."""
    _act("sir", value)


@app.command("localhost")
def localhost(value: _OnOff) -> None:
    """Allowlist kipinde localhost'a izin ver (sandbox.allow_localhost)."""
    _act("localhost", value)


@app.command("calistir", context_settings={"allow_extra_args": True})
def run(
    command: Annotated[list[str], typer.Argument(help="Çalıştırılacak komut (-- sonrası)")],
) -> None:
    """Komutu geçerli politikayla sandbox içinde çalıştır (kip kapalı olsa da)."""
    config = load_config()
    root = Path.cwd()
    context = ToolContext(
        root=root,
        shell_sandbox=SHELL_SANDBOX_WRITE_ROOT,
        sandbox_policy=sandbox_policy(
            config.sandbox, home=Path.home(), root=root, extra_deny=fusion_secret_paths()
        ),
    )
    # Tek argüman kabuk metnidir (`"echo a > b"`); birden çok kelime tırnaklanarak birleşir.
    text = command[0] if len(command) == 1 else shlex.join(command)
    result = run_shell({"command": text}, context)
    console.print(escape(result.output), soft_wrap=True)
    if not result.ok:
        raise typer.Exit(1)

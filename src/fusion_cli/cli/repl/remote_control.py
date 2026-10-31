"""REPL `/rc`: bu oturumun sürecinde uzaktan kontrol sunucusunu aç/izle/kapat (P-039).

Claude Code `/remote-control` örneği. Sunucu `ReplState.remote_control` üzerinde yaşar;
REPL kapanırken `shutdown` ile kapatılır. Telefondan gelen görevler ayrı bir
`AppSession` sohbetinde yürür (masaüstüyle aynı model); bu REPL'in sohbeti karışmaz.
"""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape

from ...core.errors import FusionError
from ...remote.constants import DEFAULT_REMOTE_PORT
from ...ui import messages, theme
from ..remote_control import RemoteControlOptions, build_host, print_start, print_status
from .state import ReplState


async def run(state: ReplState, argument: str, console: Console) -> None:
    """`/rc` → başlat (ya da durum); `/rc kod|onayla|durum|durdur`."""
    action = argument.strip().lower()
    host = state.remote_control
    try:
        if action in {"", "baslat", "başlat"}:
            if host is not None:
                snapshot = await host.snapshot()
                console.print(
                    f"[{theme.DIM}]{messages.RC_ALREADY_RUNNING.format(address=escape(snapshot.address))}[/{theme.DIM}]"
                )
                print_status(console, snapshot)
                return
            options = RemoteControlOptions(root=state.root, home=state.home)
            host = build_host(options)
            start = await host.start(port=DEFAULT_REMOTE_PORT, tunnel=True)
            state.remote_control = host
            print_start(console, start, port=DEFAULT_REMOTE_PORT)
            console.print(f"[{theme.DIM}]{messages.RC_REPL_HINT}[/{theme.DIM}]")
            return
        if host is None:
            console.print(f"[{theme.DIM}]{messages.RC_NOT_RUNNING}[/{theme.DIM}]")
            return
        if action == "durum":
            print_status(console, await host.snapshot())
        elif action == "kod":
            code, _expires = await host.new_code()
            console.print(f"[bold]{messages.RC_CODE.format(code=code)}[/bold]")
        elif action == "onayla":
            if await host.approve_pending():
                console.print(f"[{theme.OK}]{messages.RC_APPROVED}[/{theme.OK}]")
            else:
                console.print(f"[{theme.DIM}]{messages.RC_NOTHING_TO_APPROVE}[/{theme.DIM}]")
        elif action == "durdur":
            await shutdown(state)
            console.print(f"[{theme.DIM}]{messages.RC_STOPPED}[/{theme.DIM}]")
        else:
            console.print(
                f"[{theme.WARN}]{escape(messages.RC_UNKNOWN_ARG.format(argument=argument.strip()))}[/{theme.WARN}]"
            )
    except FusionError as error:
        console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")


async def shutdown(state: ReplState) -> None:
    """REPL kapanırken ya da `/rc durdur`da sunucuyu kapat; açık değilse hiçbir şey yapmaz."""
    host = state.remote_control
    if host is None:
        return
    state.remote_control = None
    await host.stop()

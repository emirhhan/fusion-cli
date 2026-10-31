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
from ...remote.host import (
    CHANNEL_REQUEST_PWA,
    CHANNEL_REQUEST_TELEGRAM,
    TEXT_TELEGRAM_MISSING,
    PairingCode,
    RemoteControlHost,
)
from ...remote.tunnel import tailscale_https_url
from ...ui import messages, theme
from ..remote_control import (
    RemoteControlOptions,
    build_host,
    print_code,
    print_start,
    print_status,
)
from .state import ReplState


async def run(state: ReplState, argument: str, console: Console) -> None:
    """`/rc` → başlat (ya da durum); `/rc kod [telegram]|onayla|durum|telegram|durdur`."""
    words = argument.strip().lower().split()
    action = words[0] if words else ""
    option = words[1] if len(words) > 1 else ""
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
            # `start` düşerse sunucuyu kendisi kapatır; host yalnız başarıda saklanır.
            start = await host.start(port=DEFAULT_REMOTE_PORT, tunnel=True)
            state.remote_control = host
            print_start(console, start, port=DEFAULT_REMOTE_PORT, public_url=tailscale_https_url())
            console.print(f"[{theme.DIM}]{messages.RC_REPL_HINT}[/{theme.DIM}]")
            return
        if host is None:
            console.print(f"[{theme.DIM}]{messages.RC_NOT_RUNNING}[/{theme.DIM}]")
            return
        if action == "durum":
            print_status(console, await host.snapshot())
        elif action == "kod":
            await _print_new_code(host, console, option)
        elif action == "telegram":
            if await host.connect_telegram():
                console.print(f"[{theme.OK}]{messages.RC_TELEGRAM_ON}[/{theme.OK}]")
                print_code(console, PairingCode(CHANNEL_REQUEST_TELEGRAM, host.telegram_code, 0.0))
            else:
                console.print(f"[{theme.WARN}]{escape(TEXT_TELEGRAM_MISSING)}[/{theme.WARN}]")
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


async def _print_new_code(host: RemoteControlHost, console: Console, option: str) -> None:
    """`/rc kod` PWA kodu; `/rc kod telegram` bağlı köprü için Telegram kodu."""
    if option == CHANNEL_REQUEST_TELEGRAM:
        if not host.telegram_connected:
            console.print(f"[{theme.DIM}]{messages.RC_TELEGRAM_NOT_CONNECTED}[/{theme.DIM}]")
            return
        code, expires = await host.new_code(CHANNEL_REQUEST_TELEGRAM)
        print_code(console, PairingCode(CHANNEL_REQUEST_TELEGRAM, code, expires))
        return
    code, expires = await host.new_code()
    print_code(console, PairingCode(CHANNEL_REQUEST_PWA, code, expires))


async def shutdown(state: ReplState) -> None:
    """REPL kapanırken ya da `/rc durdur`da sunucuyu kapat; açık değilse hiçbir şey yapmaz."""
    host = state.remote_control
    if host is None:
        return
    state.remote_control = None
    await host.stop()

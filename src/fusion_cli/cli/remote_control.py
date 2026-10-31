"""`fusion remote-control`: masaüstüsüz uzaktan kontrol sunucusunun terminal yüzü (P-039).

Komut ince tutulur: yürütücüyü (`AppSession`) ve denetleyiciyi kurar, `RemoteControlHost`
ile başlatır, durum farklarını satır satır basar. İş mantığı `remote.host`'tadır.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt

from ..config.credentials import FernetSecretStore
from ..config.keys import secret_key
from ..config.paths import credentials_file
from ..core.errors import FusionError
from ..remote.constants import DEFAULT_REMOTE_PORT
from ..remote.controller import RemoteController
from ..remote.host import RemoteControlHost, RemoteControlSnapshot, RemoteControlStart
from ..ui import messages, theme

#: Terminalde durum farkı yoklama aralığı; telefon isteklerini işleyen döngüyü boğmaz.
POLL_SECONDS = 2.0
#: Onaylanan cevaplar (Türkçe/İngilizce); varsayılan HAYIR — yetki vermek açık seçimdir.
_AFFIRMATIVE = frozenset({"e", "evet", "y", "yes"})

SessionFactory = Callable[[Callable[[str], None]], Any]


@dataclass(frozen=True, slots=True)
class RemoteControlOptions:
    root: Path
    home: Path
    port: int = DEFAULT_REMOTE_PORT
    tunnel: bool = True
    telegram: bool = False
    extra_scopes: tuple[str, ...] = ()
    approval_hours: float = 0.0


def app_session_factory(root: Path, home: Path) -> SessionFactory:
    """Masaüstünün kullandığı yürütücünün aynısı; içe aktarma ağır olduğu için tembel."""

    def factory(writer: Callable[[str], None]) -> Any:  # noqa: ANN401 - AppSession tipi ağır içe aktarma
        from ..appserver.session import AppSession

        return AppSession(writer, root=root, home=home)

    return factory


def build_host(
    options: RemoteControlOptions, *, session_factory: SessionFactory | None = None
) -> RemoteControlHost:
    """Denetleyici + sunucu: hesabın sır deposu (Telegram belirteci) masaüstüyle ortaktır."""
    controller = RemoteController(
        home=options.home,
        root=options.root,
        secrets=FernetSecretStore(credentials_file(), secret_key=secret_key()),
        session_factory=session_factory or app_session_factory(options.root, options.home),
    )
    return RemoteControlHost(
        controller, extra_scopes=options.extra_scopes, approval_hours=options.approval_hours
    )


def qr_lines(text: str) -> list[str] | None:
    """Terminal QR'ı (segno kuruluysa); yoksa `None` ve çağıran adres+kodla yetinir."""
    try:
        import segno  # type: ignore[import-not-found]  # isteğe bağlı bağımlılık; yalnız burada
    except ImportError:
        return None
    buffer = io.StringIO()
    segno.make(text, error="m").terminal(out=buffer, compact=True, border=1)
    return buffer.getvalue().splitlines()


def print_start(console: Console, start: RemoteControlStart, *, port: int) -> None:
    console.print(f"[bold {theme.ACCENT}]{messages.RC_TITLE}[/bold {theme.ACCENT}]")
    console.print(messages.RC_ADDRESS.format(address=escape(start.address)))
    lines = qr_lines(start.address)
    if lines is None:
        console.print(f"[{theme.DIM}]{messages.RC_QR_MISSING}[/{theme.DIM}]")
    else:
        for line in lines:
            console.print(line, highlight=False, markup=False)
    console.print(f"[bold]{messages.RC_CODE.format(code=start.code)}[/bold]")
    console.print(
        f"[{theme.DIM}]{messages.RC_SCOPES.format(scopes=', '.join(start.scopes))}[/{theme.DIM}]"
    )
    if start.telegram:
        console.print(f"[{theme.OK}]{messages.RC_TELEGRAM_ON}[/{theme.OK}]")
    for warning in start.warnings:
        console.print(f"[{theme.WARN}]{escape(warning)}[/{theme.WARN}]")
    console.print(f"[{theme.DIM}]{escape(messages.RC_HOW_TO.format(port=port))}[/{theme.DIM}]")


def print_status(console: Console, snapshot: RemoteControlSnapshot) -> None:
    console.print(
        f"[{theme.DIM}]"
        + escape(
            messages.RC_STATUS.format(
                address=snapshot.address or "—",
                count=snapshot.device_count,
                pending=len(snapshot.pending),
                tasks=len(snapshot.tasks),
            )
        )
        + f"[/{theme.DIM}]"
    )


async def _ask_device_approval(console: Console, name: str) -> bool:
    """Yüksek yetkili eşleştirmede terminal onayı; boş cevap HAYIR'dır."""
    prompt = messages.RC_APPROVE_PROMPT.format(name=escape(name))
    try:
        answer = await asyncio.to_thread(
            Prompt.ask, prompt, console=console, default="", show_default=False
        )
    except (EOFError, KeyboardInterrupt, OSError):
        return False
    return answer.strip().lower() in _AFFIRMATIVE


async def tick(
    host: RemoteControlHost,
    console: Console,
    previous: RemoteControlSnapshot,
    *,
    now: float,
    ask: Callable[[Console, str], Any] = _ask_device_approval,
) -> RemoteControlSnapshot:
    """Bir yoklama turu: farkları bas, bekleyen cihazı sor, süresi dolan kodu yenile."""
    current = await host.snapshot()
    for line in host.changes(previous, current):
        console.print(f"[{theme.INFO}]{escape(line)}[/{theme.INFO}]")
    if current.awaiting_device and current.awaiting_device != previous.awaiting_device:
        if await ask(console, current.awaiting_device) and await host.approve_pending():
            console.print(f"[{theme.OK}]{messages.RC_APPROVED}[/{theme.OK}]")
        else:
            await host.reject_pending()
            console.print(f"[{theme.WARN}]{messages.RC_REJECTED}[/{theme.WARN}]")
            code, _expires = await host.new_code()
            console.print(f"[bold]{messages.RC_CODE_RENEWED.format(code=code)}[/bold]")
        return await host.snapshot()
    if (
        host.code_expired(now)
        and not current.awaiting_device
        and current.device_count == previous.device_count
    ):
        code, _expires = await host.new_code()
        console.print(f"[bold]{messages.RC_CODE_RENEWED.format(code=code)}[/bold]")
    return current


async def run_remote_control(
    options: RemoteControlOptions,
    console: Console,
    *,
    host: RemoteControlHost | None = None,
    stop: asyncio.Event | None = None,
    clock: Callable[[], float] = time.time,
) -> int:
    """Komutun gövdesi: başlat, Ctrl-C'ye kadar izle, temiz kapat. Çıkış kodunu döndürür."""
    host = host or build_host(options)
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError, RuntimeError):
        loop.add_signal_handler(signal.SIGINT, stop.set)
    try:
        start = await host.start(
            port=options.port, tunnel=options.tunnel, telegram=options.telegram
        )
        print_start(console, start, port=options.port)
        previous = await host.snapshot()
        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), POLL_SECONDS)
            if stop.is_set():
                break
            previous = await tick(host, console, previous, now=clock())
    except FusionError as error:
        console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
        return 1
    finally:
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.remove_signal_handler(signal.SIGINT)
        await host.stop()
        console.print(f"[{theme.DIM}]{messages.RC_STOPPED}[/{theme.DIM}]")
    return 0

"""`fusion remote-control`: masaüstüsüz uzaktan kontrol sunucusunun terminal yüzü (P-039).

Komut ince tutulur: yürütücüyü (`AppSession`) ve denetleyiciyi kurar, `RemoteControlHost`
ile başlatır, durum farklarını satır satır basar. İş mantığı `remote.host`'tadır.

Ölçüldü (31 Ekim, bağımsız inceleme): terminal onay sorusu `to_thread(Prompt.ask)` ile yoklama
döngüsünü bloklıyordu (2 dakikalık kod soru sürerken düşüyor, Ctrl-C işlemiyor, `asyncio.run`
kapanışta `input()`'u bekliyordu). Soru artık daemon iş parçacığında sorulur, cevabı Future ile
gelir; yoklama sürer, süre dolması ile kullanıcı reddi ayrı anlatılır.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import signal
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt

from ..config.credentials import FernetSecretStore
from ..config.keys import secret_key
from ..config.paths import credentials_file
from ..core.errors import FusionError
from ..remote.constants import DEFAULT_REMOTE_PORT
from ..remote.controller import RemoteController
from ..remote.host import (
    CHANNEL_REQUEST_TELEGRAM,
    PairingCode,
    RemoteControlHost,
    RemoteControlSnapshot,
    RemoteControlStart,
)
from ..remote.tunnel import tailscale_https_url
from ..ui import messages, theme

#: Terminalde durum farkı yoklama aralığı; telefon isteklerini işleyen döngüyü boğmaz.
POLL_SECONDS = 2.0
#: Onaylanan cevaplar (Türkçe/İngilizce); varsayılan HAYIR — yetki vermek açık seçimdir.
_AFFIRMATIVE = frozenset({"e", "evet", "y", "yes"})
#: Telefon adresine eklenen eşleştirme kodu parametresi (PWA `?kod=` okur).
PAIRING_LINK_PARAM = "kod"

SessionFactory = Callable[[Callable[[str], None]], Any]
#: Terminal onay sorusu: cevabı ileride veren bir Future/coroutine döndürür (bloklamaz).
AskDevice = Callable[[Console, str], Awaitable[bool]]
PromptFn = Callable[..., str]


@dataclass(frozen=True, slots=True)
class RemoteControlOptions:
    root: Path
    home: Path
    port: int = DEFAULT_REMOTE_PORT
    tunnel: bool = True
    telegram: bool = False
    extra_scopes: tuple[str, ...] = ()
    approval_hours: float = 0.0
    #: Telefonun açacağı tünel adresi (`--adres`); boşsa Tailscale'den okunmaya çalışılır.
    public_url: str = ""


@dataclass(frozen=True, slots=True)
class Watch:
    """Yoklama döngüsünün durumu: son fotoğraf ve (varsa) askıdaki terminal sorusu."""

    previous: RemoteControlSnapshot
    prompt: asyncio.Future[bool] | None = None
    prompt_device: str = ""
    #: Soru askıdayken cihazın kodu düştü: gelecek cevap uygulanmaz, yalnız soru kapanır.
    prompt_stale: bool = False


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


def pairing_link(public_url: str, code: str) -> str:
    """Telefonun tek dokunuşla açacağı adres: tünel adresi + `?kod=`."""
    return f"{public_url.rstrip('/')}/?{urlencode({PAIRING_LINK_PARAM: code})}"


def print_code(console: Console, entry: PairingCode) -> None:
    template = (
        messages.RC_TELEGRAM_CODE if entry.channel == CHANNEL_REQUEST_TELEGRAM else messages.RC_CODE
    )
    console.print(f"[bold]{escape(template.format(code=entry.code))}[/bold]")


def print_start(
    console: Console, start: RemoteControlStart, *, port: int, public_url: str = ""
) -> None:
    """Başlangıç bloğu: yerel adres, telefon adresi + QR (yalnız tünel adresi varsa), kodlar."""
    console.print(f"[bold {theme.ACCENT}]{messages.RC_TITLE}[/bold {theme.ACCENT}]")
    console.print(messages.RC_ADDRESS.format(address=escape(start.address)))
    if public_url:
        console.print(messages.RC_PHONE_ADDRESS.format(url=escape(public_url)))
        lines = qr_lines(pairing_link(public_url, start.code))
        if lines is None:
            console.print(f"[{theme.DIM}]{messages.RC_QR_MISSING}[/{theme.DIM}]")
        else:
            for line in lines:
                console.print(line, highlight=False, markup=False)
            console.print(f"[{theme.DIM}]{messages.RC_QR_HINT}[/{theme.DIM}]")
    else:
        console.print(
            f"[{theme.WARN}]{escape(messages.RC_NO_PUBLIC_ADDRESS.format(port=port))}[/{theme.WARN}]"
        )
    console.print(f"[bold]{messages.RC_CODE.format(code=start.code)}[/bold]")
    if start.telegram_code:
        console.print(
            f"[bold]{escape(messages.RC_TELEGRAM_CODE.format(code=start.telegram_code))}[/bold]"
        )
    console.print(
        f"[{theme.DIM}]{messages.RC_SCOPES.format(scopes=', '.join(start.scopes))}[/{theme.DIM}]"
    )
    if start.telegram:
        console.print(f"[{theme.OK}]{messages.RC_TELEGRAM_ON}[/{theme.OK}]")
    for warning in start.warnings:
        console.print(f"[{theme.WARN}]{escape(warning)}[/{theme.WARN}]")
    console.print(f"[{theme.DIM}]{escape(messages.RC_HOW_TO)}[/{theme.DIM}]")


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
    if snapshot.awaiting_device:
        console.print(
            f"[{theme.WARN}]"
            + escape(messages.RC_STATUS_AWAITING.format(name=snapshot.awaiting_device))
            + f"[/{theme.WARN}]"
        )


def _ask_device_approval(
    console: Console, name: str, *, prompt: PromptFn = Prompt.ask
) -> asyncio.Future[bool]:
    """Yüksek yetkili eşleştirmede terminal onayı; boş cevap HAYIR'dır.

    Soru daemon iş parçacığında bekler: olay döngüsü bloklanmaz ve Ctrl-C ile kapanış
    `input()`'u beklemez (varsayılan executor'daki iş parçacığı beklenirdi).
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    text = messages.RC_APPROVE_PROMPT.format(name=escape(name))

    def resolve(value: bool) -> None:
        if not future.done():
            future.set_result(value)

    def worker() -> None:
        try:
            answer = str(prompt(text, console=console, default="", show_default=False))
            value = answer.strip().lower() in _AFFIRMATIVE
        except (EOFError, KeyboardInterrupt, OSError, StopIteration):
            value = False
        with contextlib.suppress(RuntimeError):  # döngü kapanmışsa cevap kimseye lazım değil
            loop.call_soon_threadsafe(resolve, value)

    threading.Thread(target=worker, name="fusion-rc-onay", daemon=True).start()
    return future


async def _settle_prompt(
    host: RemoteControlHost, console: Console, watch: Watch, current: RemoteControlSnapshot
) -> Watch:
    """Askıdaki sorunun sonucunu uygula: onay, ret ya da (cihaz artık beklemiyorsa) yok say."""
    assert watch.prompt is not None and watch.prompt.done()
    cleared = replace(watch, prompt=None, prompt_device="", prompt_stale=False)
    try:
        answer = bool(watch.prompt.result())
    except (asyncio.CancelledError, Exception):  # soru düştü: cevap HAYIR sayılır
        answer = False
    if watch.prompt_stale or current.awaiting_device != watch.prompt_device:
        return cleared  # süre dolmuş; uyarı basıldı, cevap kimseye uygulanmaz
    if answer and await host.approve_pending():
        console.print(f"[{theme.OK}]{messages.RC_APPROVED}[/{theme.OK}]")
    else:
        await host.reject_pending()
        console.print(f"[{theme.WARN}]{messages.RC_REJECTED}[/{theme.WARN}]")
    return cleared


async def tick(
    host: RemoteControlHost,
    console: Console,
    watch: Watch,
    *,
    now: float,
    ask: AskDevice = _ask_device_approval,
) -> Watch:
    """Bir yoklama turu: farkları bas, bekleyen cihazı sor, cevabı uygula, kodları yenile."""
    current = await host.snapshot()
    for line in host.changes(watch.previous, current):
        console.print(f"[{theme.INFO}]{escape(line)}[/{theme.INFO}]")
    if (prompt := watch.prompt) is not None:
        if not watch.prompt_stale and current.awaiting_device != watch.prompt_device:
            # Bir kez söyle: soru askıda ama cihazın kodu düştü (kullanıcı reddi değil).
            expired = messages.RC_APPROVAL_EXPIRED.format(name=watch.prompt_device)
            console.print(f"[{theme.WARN}]{escape(expired)}[/{theme.WARN}]")
            watch = replace(watch, prompt_stale=True)
        if prompt.done():
            watch = await _settle_prompt(host, console, watch, current)
    elif current.awaiting_device:
        # Yeni soru yalnız tur başında soru yokken: aynı turda cevaplanan cihaz için
        # `current` hâlâ "bekliyor" der, ikinci kez sorulmaz.
        future = asyncio.ensure_future(ask(console, current.awaiting_device))
        watch = replace(watch, prompt=future, prompt_device=current.awaiting_device)
    for entry in await host.renew_codes(now=now):
        print_code(console, entry)
    return replace(watch, previous=current)


async def run_remote_control(
    options: RemoteControlOptions,
    console: Console,
    *,
    host: RemoteControlHost | None = None,
    stop: asyncio.Event | None = None,
    clock: Callable[[], float] = time.time,
    poll_seconds: float = POLL_SECONDS,
    ask: AskDevice = _ask_device_approval,
    public_url_lookup: Callable[[], str] = tailscale_https_url,
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
        public_url = options.public_url or (public_url_lookup() if options.tunnel else "")
        print_start(console, start, port=options.port, public_url=public_url)
        watch = Watch(await host.snapshot())
        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), poll_seconds)
            if stop.is_set():
                break
            watch = await tick(host, console, watch, now=clock(), ask=ask)
    except FusionError as error:
        console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
        return 1
    finally:
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.remove_signal_handler(signal.SIGINT)
        await host.stop()
        console.print(f"[{theme.DIM}]{messages.RC_STOPPED}[/{theme.DIM}]")
    return 0

"""`terminalSequence` (#128): izinli dizi etkileşimli oturumda terminale basılır, `-p`'de yok."""

from __future__ import annotations

import io

from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.engines.hooks.terminal import tty_writer

from .test_hooks_loop import _kanca

_DIZI = "print(json.dumps({'terminalSequence': '\\x1b]777;notify;Fusion;izin\\x07'}))\n"


def _oturum(tmp_path, writes: list[str], *, interactive: bool) -> HookSession:
    command = _kanca(tmp_path, HookEvent.NOTIFICATION, _DIZI)
    return HookSession(
        root=tmp_path,
        loader=lambda: HookSet((command,)),
        interactive=interactive,
        terminal_writer=writes.append,
    )


async def test_notification_dizisi_etkilesimli_oturumda_basilir(tmp_path):
    writes: list[str] = []
    await _oturum(tmp_path, writes, interactive=True).notify("permission_prompt", "izin")
    assert writes == ["\x1b]777;notify;Fusion;izin\x07"]


async def test_tek_atista_dizi_basilmaz(tmp_path):
    writes: list[str] = []
    await _oturum(tmp_path, writes, interactive=False).notify("permission_prompt", "izin")
    assert writes == []


def test_tty_olmayan_akista_yazici_yok():
    assert tty_writer(io.StringIO()) is None


def test_tty_akista_yazici_diziyi_yazar():
    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    akis = _Tty()
    writer = tty_writer(akis)
    assert writer is not None
    writer("\x07")
    assert akis.getvalue() == "\x07"

"""Turun masaüstü oturumu (P-033): Esc ile durdurma, gizle/geri göster, gösterge, görüntü dışlama.

Gerçek uygulama gizlenmez, olay musluğu kurulmaz: `DesktopTurnIo` sahte, Esc yardımcısı yerine
küçük bir kabuk betiği kullanılır.
"""

from __future__ import annotations

import asyncio
import stat
import threading
from pathlib import Path

import pytest

from fusion_cli.appserver.computer_activity import COMPUTER_EVENT, ComputerActivityWatch
from fusion_cli.core.desktop_settings import DesktopSettings
from fusion_cli.core.events import ToolStarted, TurnFinished
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop, desktop_lock, desktop_screen, desktop_turn
from fusion_cli.tools.desktop_escape import EscapeWatch
from fusion_cli.tools.desktop_policy import capture_exclusions
from fusion_cli.tools.desktop_screen import Display
from fusion_cli.tools.desktop_turn import DesktopTurn, DesktopTurnIo


class _FakeIo:
    def __init__(self) -> None:
        self.hidden_calls: list[tuple[int, ...]] = []
        self.unhidden: list[tuple[int, ...]] = []
        self.escape_handlers: list[object] = []
        self.stopped = 0

    def io(self) -> DesktopTurnIo:
        def hide(keep):
            self.hidden_calls.append(tuple(keep))
            return (501, 502)

        def unhide(pids):
            self.unhidden.append(tuple(pids))

        def start_escape(handler):
            self.escape_handlers.append(handler)
            return self._stop

        return DesktopTurnIo(
            hide=hide, unhide=unhide, start_escape=start_escape, keep_pids=lambda: (1, 2)
        )

    def _stop(self) -> None:
        self.stopped += 1


def test_ilk_on_plan_eyleminde_bir_kez_hazirlanir_ve_kapanista_geri_gosterir():
    fake = _FakeIo()
    cancels: list[int] = []
    turn = DesktopTurn(DesktopSettings(background=False), lambda: cancels.append(1), fake.io())

    turn.foreground_action()
    turn.foreground_action()
    assert fake.hidden_calls == [(1, 2)] and len(fake.escape_handlers) == 1
    assert turn.escape_active

    turn.close()
    turn.close()
    assert fake.unhidden == [(501, 502)] and fake.stopped == 1


def test_arka_plan_kipinde_gizlenmez_unhide_kapaliysa_geri_gosterilmez():
    fake = _FakeIo()
    DesktopTurn(DesktopSettings(), lambda: None, fake.io()).foreground_action()
    assert fake.hidden_calls == []

    fake = _FakeIo()
    turn = DesktopTurn(
        DesktopSettings(background=False, unhide_on_finish=False), lambda: None, fake.io()
    )
    turn.foreground_action()
    turn.close()
    assert fake.hidden_calls and fake.unhidden == []


def test_esc_kapaliysa_dinleyici_kurulmaz():
    fake = _FakeIo()
    DesktopTurn(DesktopSettings(escape_stops=False), lambda: None, fake.io()).foreground_action()
    assert fake.escape_handlers == []


async def test_esc_tur_gorevini_iptal_eder_ve_kilit_birakilir(tmp_path, monkeypatch):
    fake = _FakeIo()
    released: list[str] = []
    monkeypatch.setattr(desktop_lock, "release", lambda **kw: released.append(kw["token"]))
    context = ToolContext(root=tmp_path, job_scope="tur-1")
    started = asyncio.Event()

    async def turn_body() -> None:
        desktop_turn.begin(context, fake.io())
        try:
            # Araç iş parçacığında ilk ön plan eylemi; sonra kullanıcı Esc'e basar.
            await asyncio.to_thread(desktop_turn.foreground_action, context)
            started.set()
            await asyncio.sleep(10)
        finally:
            desktop_turn.finish(context)

    task = asyncio.ensure_future(turn_body())
    await started.wait()
    handler = fake.escape_handlers[0]
    threading.Thread(target=handler).start()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.stopped == 1 and released == ["tur-1"]
    assert context.desktop.turn is None


async def test_kapali_bilgisayar_kullaniminda_oturum_baglanmaz(tmp_path):
    context = ToolContext(root=tmp_path, desktop_settings=DesktopSettings(enabled=False))
    assert desktop_turn.begin(context, _FakeIo().io()) is None
    desktop_turn.foreground_action(context)  # bağlı oturum yok: sessiz


def test_klavye_araci_on_plan_hazirligini_tetikler(tmp_path, monkeypatch):
    calls: list[str] = []

    class _Turn:
        def foreground_action(self) -> None:
            calls.append("hazir")

    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop_lock, "claim", lambda **_: None)
    monkeypatch.setattr(desktop, "_framework", lambda: object())
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: True)
    monkeypatch.setattr(desktop, "_post_text", lambda loaded, value: None)
    context = ToolContext(root=tmp_path)
    context.desktop.turn = _Turn()

    assert desktop.desktop_type({"text": "a"}, context).ok
    assert calls == ["hazir"]


def _script(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "escwatch.sh"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_esc_dinleyicisi_satirlari_okur_ve_stdin_kapaninca_kapanir(tmp_path):
    script = _script(tmp_path, "echo '{\"ok\": true}'\necho '{\"esc\": true}'\ncat >/dev/null\n")
    seen = threading.Event()
    watch = EscapeWatch(seen.set, executable=lambda: script, ignored_pid=1)

    assert watch.start() is True
    assert seen.wait(5)
    watch.stop()
    assert not watch.is_running


def test_esc_dinleyicisi_kurulamazsa_tur_surer(tmp_path):
    script = _script(tmp_path, 'echo \'{"ok": false, "metin": "izin yok"}\'\n')
    watch = EscapeWatch(lambda: None, executable=lambda: script, ignored_pid=1)

    assert watch.start() is False
    assert watch.error == "izin yok"


def test_gosterge_olayi_turda_bir_kez_acilir_ve_kapanir():
    events: list[dict[str, object]] = []
    watch = ComputerActivityWatch(events.append, lambda: DesktopSettings())

    watch.handle(ToolStarted(name="desktop_screenshot", args={}))
    watch.handle(ToolStarted(name="desktop_click", args={"x": 1, "y": 1}))
    watch.handle(ToolStarted(name="desktop_key", args={"key": "a"}))
    watch.handle(TurnFinished())
    watch.clear()

    assert events == [
        {"olay": COMPUTER_EVENT, "aktif": True, "esc": True},
        {"olay": COMPUTER_EVENT, "aktif": False, "esc": False},
    ]


def test_reddedilen_ve_engelli_uygulamalar_goruntuden_dislanir(monkeypatch):
    names, prefixes = capture_exclusions(
        DesktopSettings(denied_apps=("Mail",), app_levels=("Binance=observe",))
    )
    assert "mail" in names and "1password" in names and "binance" not in names
    assert "com.binance" in prefixes and "com.fusion.desktop" not in prefixes
    assert capture_exclusions(DesktopSettings(category_defaults=False)) == ((), ())

    requests: list[dict[str, object]] = []

    def fake_invoke(operation, target):
        requests.append(target["request"])
        return {"ok": False}

    monkeypatch.setattr(desktop_screen, "invoke_sync", fake_invoke)
    monkeypatch.setattr(desktop_screen, "_exclude_pids", lambda: [7])
    display = Display(1, 0, 0, 100, 100, True, identifier=3)
    desktop_screen._native_capture(display, 800, DesktopSettings(denied_apps=("Notes",)))
    assert requests[0]["excludePids"] == [7]
    assert "notes" in requests[0]["excludeNames"]

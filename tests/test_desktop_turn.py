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
from fusion_cli.core.events import (
    DesktopEscapeStopped,
    ToolExecuted,
    ToolOutcome,
    ToolStarted,
    TurnFinished,
)
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
        self.notes: list[str] = []

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
            hide=hide,
            unhide=unhide,
            start_escape=start_escape,
            keep_pids=lambda: (1, 2),
            notify=self.notes.append,
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


async def test_esc_tur_gorevini_iptal_eder_kilit_tur_sonunda_kalir(tmp_path, monkeypatch):
    fake = _FakeIo()
    released: list[str] = []
    monkeypatch.setattr(desktop_lock, "release", lambda **kw: released.append(kw["token"]))
    context = ToolContext(
        root=tmp_path, job_scope="tur-1", desktop_settings=DesktopSettings(enabled=True)
    )
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
    # #429: kilit tur bitince değil, oturum çıkınca bırakılır.
    assert fake.stopped == 1 and released == []
    assert context.desktop.turn is None


async def test_kapali_bilgisayar_kullaniminda_oturum_baglanmaz(tmp_path):
    context = ToolContext(root=tmp_path, desktop_settings=DesktopSettings(enabled=False))
    assert desktop_turn.begin(context, _FakeIo().io()) is None
    desktop_turn.foreground_action(context)  # bağlı oturum yok: sessiz


def test_klavye_araci_on_plan_hazirligini_tetikler(tmp_path, monkeypatch):
    calls: list[str] = []

    class _Turn:
        def foreground_action(self, keep=()) -> None:
            calls.append("hazir")

    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop_lock, "claim", lambda **_: None)
    monkeypatch.setattr(desktop, "_framework", lambda: object())
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: True)
    monkeypatch.setattr(desktop, "_post_text", lambda loaded, value, **kwargs: len(value))
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


def _executed(name: str, outcome: ToolOutcome = ToolOutcome.OK) -> ToolExecuted:
    return ToolExecuted(name=name, args={}, outcome=outcome, output="")


def test_gosterge_olayi_turda_bir_kez_acilir_ve_kapanir(monkeypatch):
    monkeypatch.setattr(desktop_turn, "escape_listening", lambda: True)
    events: list[dict[str, object]] = []
    watch = ComputerActivityWatch(events.append, lambda: DesktopSettings())

    watch.handle(_executed("desktop_screenshot"))
    watch.handle(_executed("desktop_click"))
    watch.handle(_executed("desktop_key"))
    watch.handle(TurnFinished())
    watch.clear()

    assert events == [
        {"olay": COMPUTER_EVENT, "aktif": True, "esc": True},
        {"olay": COMPUTER_EVENT, "aktif": False, "esc": False},
    ]


def test_gosterge_eylem_gercekten_olunca_acilir_esc_dinleyiciye_baglidir(monkeypatch):
    """Ölçüldü (31 Ekim): şerit `ToolStarted`'da (araç kendi denetiminden önce) açılıyor ve
    Esc dinleyicisi kurulamasa da `escape_stops` ayarına bakıp "durdurmak için Esc" diyordu."""
    monkeypatch.setattr(desktop_turn, "escape_listening", lambda: False)
    events: list[dict[str, object]] = []
    watch = ComputerActivityWatch(events.append, lambda: DesktopSettings(escape_stops=True))

    watch.handle(ToolStarted(name="desktop_click", args={}))
    watch.handle(_executed("desktop_click", ToolOutcome.FAILED))
    watch.handle(_executed("desktop_click", ToolOutcome.BLOCKED))
    assert events == []
    watch.handle(_executed("desktop_click"))
    assert events == [{"olay": COMPUTER_EVENT, "aktif": True, "esc": False}]


def test_esc_ile_durdurma_bildirilir(monkeypatch):
    """Ölçüldü (31 Ekim): `stopped_by_escape` hiç okunmuyordu; kullanıcı genel iptal görüyordu."""
    events: list[dict[str, object]] = []
    watch = ComputerActivityWatch(events.append, lambda: DesktopSettings())
    watch.handle(DesktopEscapeStopped())
    assert events == [{"olay": COMPUTER_EVENT, "aktif": False, "esc": False, "esc_ile_durdu": True}]


async def test_finish_esc_ile_durduysa_true_dondurur_dinleyici_durumu_izlenir(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(desktop_lock, "release", lambda **kw: None)
    fake = _FakeIo()
    context = ToolContext(root=tmp_path, desktop_settings=DesktopSettings(enabled=True))
    turn = desktop_turn.begin(context, fake.io())
    assert turn is not None and not desktop_turn.escape_listening()
    desktop_turn.foreground_action(context)
    assert desktop_turn.escape_listening()
    turn._escape()
    assert desktop_turn.finish(context) is True
    assert not desktop_turn.escape_listening()
    desktop_turn.begin(context, fake.io())
    assert desktop_turn.finish(context) is False


def test_reddedilen_ve_engelli_uygulamalar_goruntuden_dislanir(monkeypatch):
    # #425: yalnız ret listesi görüntüden çıkar; View only "See the app in screenshots".
    names, prefixes = capture_exclusions(DesktopSettings(denied_apps=("Mail",)))
    assert names == ("mail",) and "binance" not in names and "1password" not in names
    assert "com.binance" not in prefixes and "com.fusion.desktop" not in prefixes
    assert capture_exclusions(DesktopSettings()) == ((), ())

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


# --- İnceleme (31 Ekim): onaylanan hedef gizlenmez ------------------------------------------


async def test_gizlemede_degerlendirilen_hedef_uygulama_korunur(tmp_path, monkeypatch):
    """Ölçüldü (31 Ekim): öndeki Safari iken Mail'e tık onaylanınca Mail gizleniyor, tık altta
    kalan (değerlendirilmemiş) uygulamaya gidiyordu."""
    from fusion_cli.core.desktop_frame import DesktopFrame
    from fusion_cli.tools import desktop_policy

    async def mail(_request):
        return {"ok": True, "app": "Mail", "bundle": "com.apple.mail", "pid": 41}

    monkeypatch.setattr(desktop_policy, "_swift_probe", mail)
    fake = _FakeIo()
    context = ToolContext(
        root=tmp_path, desktop_settings=DesktopSettings(enabled=True, background=False)
    )
    context.desktop.frame = DesktopFrame(100, 100, 0.0, 0.0, 100.0, 100.0)
    turn = desktop_turn.begin(context, fake.io())
    assert turn is not None

    assessment = await desktop_policy.assess("desktop_click", {"x": 5, "y": 5}, context)
    assert assessment is not None and assessment.target is not None
    desktop_turn.foreground_action(context)

    assert fake.hidden_calls == [(1, 2, 41)]
    desktop_turn.finish(context)


def test_cli_de_gizleme_ve_geri_gosterme_her_zaman_acik():
    """#428: CLI'de diğer uygulamalar gizlenir, tur sonunda geri gelir ("Always on")."""
    eski = DesktopSettings(enabled=True, background=True, unhide_on_finish=False)
    assert desktop_turn.turn_settings(eski).background is False
    assert desktop_turn.turn_settings(eski).unhide_on_finish is True
    desktop_turn.use_app_surface(True)
    try:
        assert desktop_turn.turn_settings(eski) == eski
    finally:
        desktop_turn.use_app_surface(False)


def test_kilit_belirteci_cli_de_surec_masaustunde_sohbet(tmp_path, monkeypatch):
    claimed: list[dict[str, object]] = []
    monkeypatch.setattr(desktop_lock, "claim", lambda **kw: claimed.append(kw))
    context = ToolContext(root=tmp_path, job_scope="sohbet-1")
    desktop_turn.claim_lock(context)
    desktop_turn.use_app_surface(True)
    try:
        desktop_turn.claim_lock(context)
    finally:
        desktop_turn.use_app_surface(False)
    assert [item["token"] for item in claimed] == ["", "sohbet-1"]
    assert "Fusion CLI" in str(claimed[0]["label"]) and "masaüstü" in str(claimed[1]["label"])
    released: list[str] = []
    monkeypatch.setattr(desktop_lock, "release", lambda **kw: released.append(kw["token"]))
    desktop_turn.end_session("sohbet-1")
    assert released == ["sohbet-1"]


def test_ilk_eylemde_ve_tur_sonunda_isletim_sistemi_bildirimi(monkeypatch):
    """#447: "Claude is using your computer · press Esc to stop", bitince ikinci bildirim."""
    fake = _FakeIo()
    turn = DesktopTurn(DesktopSettings(), lambda: None, fake.io())
    turn.foreground_action()
    turn.foreground_action()
    turn.close()
    turn.close()
    assert fake.notes == [desktop_turn.NOTIFY_START, desktop_turn.NOTIFY_DONE]
    eylemsiz = _FakeIo()
    DesktopTurn(DesktopSettings(), lambda: None, eylemsiz.io()).close()
    assert eylemsiz.notes == []

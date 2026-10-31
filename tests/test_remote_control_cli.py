"""`fusion remote-control` ve REPL `/rc` yüzeyi (P-039): terminal çıktısı, onay sorusu, kapanış."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import remote_control as cli_rc
from fusion_cli.cli.repl import remote_control as repl_rc
from fusion_cli.cli.repl.commands import ASYNC_COMMANDS, build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory
from fusion_cli.remote.host import (
    RemoteControlError,
    RemoteControlSnapshot,
    RemoteControlStart,
)

from .fakes import make_config


class FakeHost:
    """Gerçek sunucu açmayan sahte: çağrıları kaydeder, hazır fotoğrafları döner."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail
        self.snapshots: list[RemoteControlSnapshot] = [
            RemoteControlSnapshot(True, "http://127.0.0.1:1", 0, "", 0.0)
        ]
        self.started = False
        self.code = "ABCD2345"
        self.needs_desktop_approval = False

    async def start(self, *, port: int, tunnel: bool, telegram: bool) -> RemoteControlStart:
        self.calls.append(f"start:{port}:{tunnel}:{telegram}")
        if self.fail:
            raise RemoteControlError("port kullanımda")
        self.started = True
        return RemoteControlStart(
            "http://127.0.0.1:1", self.code, 10.0, ("agent.run",), False, False
        )

    async def snapshot(self) -> RemoteControlSnapshot:
        return self.snapshots[-1]

    @staticmethod
    def changes(previous: RemoteControlSnapshot, current: RemoteControlSnapshot) -> list[str]:
        return ["fark"] if previous is not current else []

    async def approve_pending(self) -> bool:
        self.calls.append("approve")
        return True

    async def reject_pending(self) -> bool:
        self.calls.append("reject")
        return True

    async def new_code(self) -> tuple[str, float]:
        self.calls.append("code")
        return "YENI2345", 20.0

    def code_expired(self, now: float) -> bool:
        return now > 10.0

    async def stop(self) -> None:
        self.calls.append("stop")
        self.started = False


def _console() -> Console:
    return Console(record=True, width=120, force_terminal=False, color_system=None)


def _options(tmp_path: Path) -> cli_rc.RemoteControlOptions:
    return cli_rc.RemoteControlOptions(root=tmp_path, home=tmp_path, port=1, tunnel=True)


def test_qr_segno_yoksa_none_doner_ve_adres_kodla_yetinilir(monkeypatch: Any) -> None:
    monkeypatch.setitem(sys.modules, "segno", None)  # içe aktarma ImportError üretir
    assert cli_rc.qr_lines("http://127.0.0.1:8791") is None
    console = _console()
    cli_rc.print_start(
        console,
        RemoteControlStart("http://127.0.0.1:8791", "ABCD2345", 1.0, ("agent.run",), False, True),
        port=8791,
    )
    text = console.export_text()
    assert "ABCD2345" in text and "segno" in text and "Telegram botu bağlı" in text


async def test_komut_baslatir_durdurma_isaretine_kadar_izler_ve_kapatir(tmp_path: Path) -> None:
    host = FakeHost()
    stop = asyncio.Event()
    stop.set()
    console = _console()
    code = await cli_rc.run_remote_control(_options(tmp_path), console, host=host, stop=stop)  # type: ignore[arg-type]
    assert code == 0 and host.calls == ["start:1:True:False", "stop"]
    text = console.export_text()
    assert "Eşleştirme kodu: ABCD2345" in text and "durduruldu" in text


async def test_baslatma_hatasi_turkce_mesaj_ve_cikis_kodu_bir(tmp_path: Path) -> None:
    host = FakeHost(fail=True)
    console = _console()
    code = await cli_rc.run_remote_control(
        _options(tmp_path),
        console,
        host=host,  # type: ignore[arg-type]
        stop=asyncio.Event(),
    )
    assert code == 1 and "port kullanımda" in console.export_text() and host.calls[-1] == "stop"


async def test_yoklama_turu_bekleyen_cihazi_sorar_onaylar_ve_dolan_kodu_yeniler() -> None:
    host = FakeHost()
    console = _console()
    idle = RemoteControlSnapshot(True, "http://127.0.0.1:1", 0, "", 0.0)
    waiting = RemoteControlSnapshot(
        True, "http://127.0.0.1:1", 0, "", 0.0, awaiting_device="Tablet"
    )
    host.snapshots = [idle, waiting]

    async def evet(_console: Console, name: str) -> bool:
        return name == "Tablet"

    await cli_rc.tick(host, console, idle, now=0.0, ask=evet)  # type: ignore[arg-type]
    assert host.calls == ["approve"] and "onaylandı" in console.export_text()

    async def hayir(_console: Console, _name: str) -> bool:
        return False

    host.calls.clear()
    await cli_rc.tick(host, console, idle, now=0.0, ask=hayir)  # type: ignore[arg-type]
    assert host.calls == ["reject", "code"] and "YENI2345" in console.export_text()

    host.calls.clear()
    host.snapshots = [idle]
    await cli_rc.tick(host, console, idle, now=11.0, ask=hayir)  # type: ignore[arg-type]
    assert host.calls == ["code"]  # süresi dolan kod kendiliğinden yenilenir


def test_cli_yardim_komutu_tanitir() -> None:
    result = CliRunner().invoke(app_module.app, ["remote-control", "--help"])
    assert result.exit_code == 0
    assert "--telegram" in result.stdout and "--kapsam" in result.stdout


async def test_repl_rc_komutu_kayitli_ve_sunucu_yokken_yol_gosterir(tmp_path: Path) -> None:
    registry = build_registry()
    assert registry.get("rc") is registry.get("remote-control") and "rc" in ASYNC_COMMANDS
    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    console = _console()
    await repl_rc.run(state, "durum", console)
    assert "çalışmıyor" in console.export_text()


async def test_repl_rc_alt_komutlari_sahte_sunucuyu_surer_ve_kapanista_durdurur(
    tmp_path: Path,
) -> None:
    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    host = FakeHost()
    state.remote_control = host  # type: ignore[assignment]
    console = _console()
    await repl_rc.run(state, "", console)
    assert "zaten çalışıyor" in console.export_text()
    await repl_rc.run(state, "kod", console)
    await repl_rc.run(state, "onayla", console)
    await repl_rc.run(state, "bilinmeyen", console)
    assert host.calls == ["code", "approve"] and "tanınmadı" in console.export_text()
    await repl_rc.shutdown(state)
    assert host.calls[-1] == "stop" and state.remote_control is None
    await repl_rc.shutdown(state)  # ikinci kapanış zararsız
    assert host.calls.count("stop") == 1

"""Ajanın süren `run_shell` komutu Ctrl+B ile kesilmeden arka plana devredilir (#218)."""

from __future__ import annotations

import sys
import threading
import time

import pytest

from fusion_cli.core.constants import EXIT_CODE_PREFIX
from fusion_cli.core.shell_handoff import ShellHandoff
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.shell import run_shell
from fusion_cli.tools.shell_detach import kill_handed_off, stop_handed_off

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX kabuğu")


def _bekle(kosul, sure: float = 10.0) -> bool:
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.05)
    return False


def _istek_gonder(handoff: ShellHandoff) -> None:
    def _calis() -> None:
        _bekle(handoff.request)

    threading.Thread(target=_calis, daemon=True).start()


def test_devredilen_komut_surer_ve_ciktisi_gunluge_yazilir(tmp_path):
    handoff = ShellHandoff()
    context = ToolContext(root=tmp_path, shell_handoff=handoff, shell_fingerprint=False)
    _istek_gonder(handoff)
    baslangic = time.monotonic()
    result = run_shell({"command": "echo once; sleep 2; echo sonra"}, context)
    assert time.monotonic() - baslangic < 1.5  # bekleme bitince değil devirde döndü
    assert result.ok and "arka plana alındı" in result.output
    job = handoff.jobs[0]
    assert job.id in result.output and str(job.log_path) in result.output
    assert _bekle(lambda: job.returncode is not None)
    metin = job.log_path.read_text(encoding="utf-8")
    assert "once" in metin and "sonra" in metin and f"{EXIT_CODE_PREFIX}0)" in metin


def test_devir_istegi_yokken_komut_olagan_biter(tmp_path):
    handoff = ShellHandoff()
    context = ToolContext(root=tmp_path, shell_handoff=handoff, shell_fingerprint=False)
    result = run_shell({"command": "echo tamam"}, context)
    assert result.ok and "tamam" in result.output
    assert handoff.jobs == [] and not handoff.request()  # süren komut yok


def test_devredilen_komut_durdurulur_ve_kapanista_oldurulur(tmp_path):
    handoff = ShellHandoff()
    context = ToolContext(root=tmp_path, shell_handoff=handoff, shell_fingerprint=False)
    _istek_gonder(handoff)
    run_shell({"command": "sleep 30"}, context)
    _istek_gonder(handoff)
    run_shell({"command": "sleep 30"}, context)
    first, second = handoff.jobs
    assert stop_handed_off(handoff, first.id) is first and first.stopped
    assert kill_handed_off(handoff) == 1 and second.stopped
    assert kill_handed_off(handoff) == 0


def test_tasks_devredilen_ajan_komutunu_listeler(tmp_path):
    from fusion_cli.cli.repl.background_commands import tasks_command
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    context = ToolContext(root=tmp_path, shell_handoff=state.shell_handoff, shell_fingerprint=False)
    _istek_gonder(state.shell_handoff)
    run_shell({"command": "sleep 30"}, context)
    job = state.shell_handoff.jobs[0]
    assert "sleep 30" in tasks_command(state, "") and job.id in tasks_command(state, "")
    assert "durduruldu" in tasks_command(state, f"stop {job.id}")


@pytest.mark.asyncio
async def test_tam_ekranda_ctrl_b_ajanin_suren_komutunu_turu_kesmeden_devreder(tmp_path):
    import asyncio

    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.cli.repl.tui_loop import _TuiSession
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    session = _TuiSession(state)
    event = state.shell_handoff.begin()
    session._task = asyncio.ensure_future(asyncio.sleep(5))
    session._current_line = "testleri koştur"
    session._background_turn()
    assert event.is_set()
    assert session._to_background is False  # tur kesilip baştan başlatılmadı
    assert not session._task.cancelled() and not session._task.done()
    session._task.cancel()

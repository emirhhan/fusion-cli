"""Ajanın süren `run_shell` komutu Ctrl+B ile kesilmeden arka plana devredilir (#218, #320).

Tek uygulama `core.foreground_handoff` + `tools.shell_adopt`: devredilen komut `.fusion/is`
kabuk işi olur (komut kesilmez, tur sürer), `/tasks` listeler ve durdurur. Ayrıntılı araç
davranışı `test_shell_auto_background.py`'dedir; burada REPL yüzeyleri sınanır.
"""

from __future__ import annotations

import sys
import threading
import time

import pytest

from fusion_cli.core import foreground_handoff
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.shell import run_shell

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX kabuğu")


def _bekle(kosul, sure: float = 10.0) -> bool:
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.05)
    return False


def _istek_gonder() -> None:
    threading.Thread(
        target=lambda: _bekle(foreground_handoff.request_background), daemon=True
    ).start()


def _state(tmp_path):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    return ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )


def test_devir_istegi_yokken_komut_olagan_biter(tmp_path):
    context = ToolContext(root=tmp_path, shell_fingerprint=False)
    result = run_shell({"command": "echo tamam"}, context)
    assert result.ok and "tamam" in result.output
    assert not foreground_handoff.request_background()  # süren komut yok


def test_tasks_devredilen_ajan_komutunu_listeler_ve_durdurur(tmp_path):
    from fusion_cli.cli.repl.background_commands import tasks_command

    state = _state(tmp_path)
    context = ToolContext(root=tmp_path, shell_fingerprint=False)
    _istek_gonder()
    baslangic = time.monotonic()
    result = run_shell({"command": "echo once; sleep 30"}, context)
    assert time.monotonic() - baslangic < 10  # devirde döndü, komut beklenmedi
    assert result.ok
    liste = tasks_command(state, "")
    assert "Kabuk işleri:" in liste and "sürüyor" in liste
    job_id = liste.split("kabuk ", 1)[1].split(" ", 1)[0]
    assert job_id in result.output
    durdur = tasks_command(state, f"stop {job_id}")
    assert job_id in durdur


@pytest.mark.asyncio
async def test_tam_ekranda_ctrl_b_ajanin_suren_komutunu_turu_kesmeden_devreder(tmp_path):
    import asyncio

    from fusion_cli.cli.repl.tui_loop import _TuiSession

    state = _state(tmp_path)
    session = _TuiSession(state)
    session._task = asyncio.ensure_future(asyncio.sleep(5))
    session._current_line = "testleri koştur"
    with foreground_handoff.handoff_slot() as event:
        session._background_turn()
        assert event.is_set()
    assert session._to_background is False  # tur kesilip baştan başlatılmadı
    assert not session._task.cancelled() and not session._task.done()
    session._task.cancel()

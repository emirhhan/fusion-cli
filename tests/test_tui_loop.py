"""Ink-benzeri tek yol REPL döngüsü — komut yönlendirme, önizleme ve prompter."""

from __future__ import annotations

import asyncio

from fusion_cli.cli.repl.state import Engine, ReplState
from fusion_cli.cli.repl.tui import FusionTui
from fusion_cli.cli.repl.tui_loop import TuiPrompter, _preview, _TuiSession
from fusion_cli.engines.agent.approval import ApprovalRequest
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path) -> ReplState:
    return ReplState(config=make_config(), memory=null_memory(), root=tmp_path)


class _Tool:
    name = "run_shell"


def test_onay_onizlemesi_tehlike_gerekcesini_gosterir():
    request = ApprovalRequest(tool=_Tool(), args={"command": "rm -rf /"}, danger="kök silme")

    metin = _preview(request)

    assert "run_shell(" in metin and "kök silme" in metin


def test_onay_onizlemesi_tehlikesizde_gerekce_yok():
    request = ApprovalRequest(tool=_Tool(), args={"command": "ls"}, danger=None)

    metin = _preview(request)

    assert "run_shell(" in metin


def _noop_tui() -> FusionTui:
    return FusionTui(
        on_submit=lambda _t: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )


async def test_prompter_confirm_modali_e_ile_true_doner():
    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(
        prompter.confirm(ApprovalRequest(tool=_Tool(), args={}, danger=None))
    )
    await asyncio.sleep(0)

    # Onay modu tuşu doğrudan çözer.
    tui._resolve(True)

    assert await task is True


async def test_prompter_ask_metni_doner():
    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(prompter.ask("hangi dosya?"))
    await asyncio.sleep(0)
    tui._resolve("src/app.py")

    assert await task == "src/app.py"


async def test_bilinmeyen_komut_uyarir(tmp_path):
    session = _TuiSession(_state(tmp_path))

    await session._command("/olmayan")

    assert "bilinmeyen komut" in session.tui.transcript.lower()


async def test_agent_fusion_komutu_motoru_degistirir(tmp_path):
    state = _state(tmp_path)
    session = _TuiSession(state)

    await session._command("/fusion")
    assert state.engine is Engine.FUSION

    await session._command("/agent")
    assert state.engine is Engine.AGENT


async def test_argumansiz_secici_komut_yonlendirir(tmp_path):
    """TUI çalışırken iç içe seçici açılmaz; argümansız /model yönlendirme basar."""
    session = _TuiSession(_state(tmp_path))

    await session._command("/model")

    assert "argüman ister" in session.tui.transcript


def test_mesgulken_yeni_satir_gorev_baslatmaz(tmp_path):
    session = _TuiSession(_state(tmp_path))

    async def _bekleyen() -> None:
        await asyncio.sleep(10)

    async def _dene() -> None:
        session._task = asyncio.ensure_future(_bekleyen())
        session._submit("yeni görev")  # meşgulken yok sayılmalı
        assert session._task is not None
        # Aynı görev; yenisi başlatılmadı.
        mevcut = session._task
        session._submit("bir daha")
        assert session._task is mevcut
        session._task.cancel()

    asyncio.run(_dene())

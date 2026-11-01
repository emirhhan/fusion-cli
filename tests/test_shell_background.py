"""Ctrl+B ile süren `!` komutunu kesmeden arka plana alma (#218)."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.cli.repl.shell_background import ShellDetach, run_detachable


@pytest.mark.asyncio
async def test_arka_plana_alininca_komut_kesilmez_bitince_sonuc_verilir():
    bitti = asyncio.Event()
    alinan: list[str] = []

    async def komut() -> str:
        await bitti.wait()
        return "çıktı"

    detach = ShellDetach()
    bekleyen = asyncio.ensure_future(run_detachable(komut(), detach, alinan.append))
    await asyncio.sleep(0)
    detach.request()
    assert await bekleyen is None  # istem serbest, komut sürüyor
    assert alinan == []
    bitti.set()
    for _ in range(5):
        await asyncio.sleep(0)
    assert alinan == ["çıktı"]


@pytest.mark.asyncio
async def test_istenmezse_sonuc_dogrudan_doner():
    async def komut() -> str:
        return "tamam"

    alinan: list[str] = []
    assert await run_detachable(komut(), ShellDetach(), alinan.append) == "tamam"
    assert alinan == []


@pytest.mark.asyncio
async def test_iptal_isi_de_iptal_eder():
    async def komut() -> str:
        await asyncio.sleep(10)
        return "x"

    bekleyen = asyncio.ensure_future(run_detachable(komut(), ShellDetach(), print))
    await asyncio.sleep(0)
    bekleyen.cancel()
    with pytest.raises(asyncio.CancelledError):
        await bekleyen


@pytest.mark.asyncio
async def test_tam_ekranda_ctrl_b_suren_unlem_komutunu_kesmeden_arka_plana_alir(
    tmp_path, monkeypatch
):
    from fusion_cli.cli.repl import prefixes
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.cli.repl.tui_loop import _TuiSession
    from fusion_cli.memory.factory import null_memory
    from fusion_cli.ui import messages

    from .fakes import make_config

    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    session = _TuiSession(state)
    basladi, bitir = asyncio.Event(), asyncio.Event()

    async def _yavas(_state, command):
        basladi.set()
        await bitir.wait()
        prefixes.push_pending_context(_state, f"$ {command}\nbitti")
        return prefixes.ShellPrefixResult("derleme bitti", True, context_block="blok")

    turlar: list[str] = []

    async def _turn(line, **_kwargs):
        turlar.append(line)

    monkeypatch.setattr(prefixes, "run_shell_prefix", _yavas)
    monkeypatch.setattr(session, "_turn", _turn)
    session._submit("!make")
    await basladi.wait()
    session._background_turn()
    await session._task
    assert messages.SHELL_PREFIX_BACKGROUNDED in session.tui.transcript
    assert turlar == [] and session._shell_detach is None
    bitir.set()
    for _ in range(20):
        await asyncio.sleep(0)
        if turlar:
            break
    if session._task is not None:
        await session._task
    assert "derleme bitti" in session.tui.transcript
    assert turlar and "make" in turlar[0]  # #219: model kendiliğinden yanıtlar

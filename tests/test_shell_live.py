"""`!` komutu: canlı çıktı, Ctrl+B ile süresiz arka plan görevi, /tasks ve kapanış (#218, #219)."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from fusion_cli.cli.repl import prefixes, shell_live
from fusion_cli.cli.repl.background_commands import tasks_command
from fusion_cli.cli.repl.shell_background import ShellDetach, run_detachable
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory

from .fakes import make_config

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX kabuğu")


def _state(tmp_path) -> ReplState:
    root = tmp_path / "proje"
    root.mkdir()
    return ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=root,
        home=tmp_path / "ev",
        approval=ApprovalMode.AUTO,
    )


@pytest.mark.asyncio
async def test_cikti_komut_bitmeden_canli_akar(tmp_path):
    state = _state(tmp_path)
    parcalar: list[str] = []
    ilk = asyncio.Event()

    def _parca(text: str) -> None:
        parcalar.append(text)
        ilk.set()

    job = asyncio.ensure_future(
        prefixes.run_shell_prefix(
            state, "echo ilk; sleep 1; echo son", on_chunk=_parca, detach=asyncio.Event()
        )
    )
    await asyncio.wait_for(ilk.wait(), timeout=5)
    assert not job.done()  # ilk satır komut sürerken geldi
    assert "ilk" in "".join(parcalar)
    result = await asyncio.wait_for(job, timeout=10)
    assert result.ok and result.streamed
    assert "son" in "".join(parcalar)
    assert "ilk" in result.context_block and "son" in result.context_block


@pytest.mark.asyncio
async def test_ctrl_b_ile_arka_plana_alinan_komut_suresiz_surer_ve_tasks_listeler(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("fusion_cli.core.constants.SHELL_TIMEOUT_S", 0.3)
    state = _state(tmp_path)
    detach = ShellDetach()
    sonuc: list[prefixes.ShellPrefixResult] = []
    job = prefixes.run_shell_prefix(
        state, "sleep 0.8; echo bitti", on_chunk=lambda _t: None, detach=detach.event
    )
    waiter = asyncio.ensure_future(run_detachable(job, detach, sonuc.append))
    await asyncio.sleep(0.1)
    detach.request()
    assert await waiter is None
    listing = tasks_command(state, "")
    assert "sleep 0.8; echo bitti" in listing and "çalışıyor" in listing
    for _ in range(100):
        if sonuc:
            break
        await asyncio.sleep(0.05)
    assert sonuc and sonuc[0].ok  # 0,3 sn ön plan sınırı arka planda uygulanmadı
    assert not sonuc[0].streamed and "bitti" in sonuc[0].output
    assert "bitti (0)" in tasks_command(state, "")
    job_id = state.shell_jobs.background()[0].id
    assert "bitti" in tasks_command(state, f"show {job_id}")


@pytest.mark.asyncio
async def test_on_planda_zaman_asimi_komutu_durdurur(tmp_path, monkeypatch):
    monkeypatch.setattr("fusion_cli.core.constants.SHELL_TIMEOUT_S", 0.3)
    state = _state(tmp_path)
    result = await asyncio.wait_for(
        prefixes.run_shell_prefix(state, "sleep 5", on_chunk=lambda _t: None), timeout=10
    )
    assert not result.ok
    assert "Ctrl+B" in result.output


@pytest.mark.asyncio
async def test_tasks_stop_ve_kapanista_kill_all_sureci_oldurur(tmp_path):
    state = _state(tmp_path)
    detach = ShellDetach()
    detach.request()
    sonuc: list[prefixes.ShellPrefixResult] = []
    job = prefixes.run_shell_prefix(state, "sleep 30", on_chunk=None, detach=detach.event)
    assert await run_detachable(job, detach, sonuc.append) is None
    for _ in range(50):
        if state.shell_jobs.background():
            break
        await asyncio.sleep(0.02)
    shell_job = state.shell_jobs.background()[0]
    assert "durduruldu" in tasks_command(state, f"stop {shell_job.id}")
    for _ in range(100):
        if sonuc:
            break
        await asyncio.sleep(0.05)
    assert sonuc and not sonuc[0].ok
    with pytest.raises(ProcessLookupError):
        os.kill(shell_job.pid, 0)
    assert state.shell_jobs.kill_all() == 0


@pytest.mark.asyncio
async def test_iptal_on_plandaki_sureci_oldurur(tmp_path):
    state = _state(tmp_path)
    job = asyncio.ensure_future(
        prefixes.run_shell_prefix(state, "sleep 30", on_chunk=lambda _t: None)
    )
    for _ in range(50):
        if state.shell_jobs._jobs:
            break
        await asyncio.sleep(0.02)
    pid = next(iter(state.shell_jobs._jobs.values())).pid
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job
    await asyncio.sleep(0.1)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.asyncio
async def test_sade_rm_cop_yolundan_gecer(tmp_path):
    state = _state(tmp_path)
    hedef = state.root / "x.txt"
    hedef.write_text("veri", encoding="utf-8")
    result = await prefixes.run_shell_prefix(state, "rm x.txt", on_chunk=lambda _t: None)
    assert not hedef.exists()
    assert not result.streamed
    assert "geri-al" in result.output  # çöp yolu: `fusion cop geri-al` ile döner


def test_job_kimlikleri_benzersiz():
    assert shell_live.new_job_id() != shell_live.new_job_id()


def test_satir_ici_ctrl_b_bayti_arka_plana_alma_istegi_kurar():
    from fusion_cli.cli.repl import shell_background

    okuma, yazma = os.pipe()
    try:
        detach = ShellDetach()
        os.write(yazma, b"x")
        shell_background._on_key(okuma, detach)
        assert not detach.event.is_set()
        os.write(yazma, b"\x02")
        shell_background._on_key(okuma, detach)
        assert detach.event.is_set()
    finally:
        os.close(okuma)
        os.close(yazma)


@pytest.mark.asyncio
async def test_tty_degilse_izleyici_hicbir_sey_yapmaz():
    from fusion_cli.cli.repl import shell_background

    with shell_background.watch_ctrl_b(ShellDetach(), enabled=True):
        pass
    with shell_background.watch_ctrl_b(ShellDetach(), enabled=False):
        pass

"""Seçilmiş önkontrol araç API'sini sınırlar; gerçek model çağrısı yoktur."""

from types import SimpleNamespace

import pytest
from evals.selected_probe import install_probe_guard


async def test_probe_calls_original_once_with_empty_tools_and_same_config():
    config = object()
    calls = []

    async def run(task, config, *, allowed_tools=None, task_type="general"):
        calls.append((task, config, allowed_tools, task_type))
        return config

    session = SimpleNamespace(run_agent_task=run)
    install_probe_guard(session)
    assert await session.run_agent_task("probe", config, task_type="code") is config
    assert calls == [("probe", config, set(), "code")]


def test_unsupported_probe_api_has_no_fallback_or_patch():
    async def run(task, config):
        raise AssertionError("Çağrı olmamalı.")

    session = SimpleNamespace(run_agent_task=run)
    with pytest.raises(ValueError):
        install_probe_guard(session)
    assert session.run_agent_task is run


@pytest.mark.parametrize("mode", ["valid", "pid", "config", "tools", "timeout"])
def test_selected_preflight_requires_actual_linked_response(tmp_path, monkeypatch, mode):
    import json
    import subprocess
    from pathlib import Path

    from evals.kabul import preflight

    from .test_kabul_engine_options import proof_fixture

    monkeypatch.setattr(preflight.os, "environ", {})
    engine, driver = proof_fixture(tmp_path)
    driver["turlar"] = [{"ok": True}]
    driver["araclar"] = []
    if mode == "pid":
        driver["motor_kaniti"]["pid"] += 1
    if mode == "config":
        driver["kontrollu_ayar_kaniti"] = False
    if mode == "tools":
        driver["araclar"] = ["write_file"]
    probes = []

    def fake_run(command, **kwargs):
        assert "--model-probe" in command
        assert "--engine-source" in command
        assert Path(command[0]).name != "fusion"
        assert kwargs["timeout"] == preflight.MODEL_PROBE_TIMEOUT_S
        receipt = Path(command[command.index("--engine-proof") + 1])
        probes.append(receipt)
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        # Disk proof ayrı gerçek kimliktir; rapor PID bozulursa eşleşmez.
        receipt.write_bytes(engine.proof_path.read_bytes())
        return subprocess.CompletedProcess(command, 0, json.dumps(driver), "")

    monkeypatch.setattr(preflight, "run_owned_probe", fake_run)
    for _ in range(2):
        result = preflight._model_probe(None, engine.selection.source_root, engine.manifest)
        assert result.passed is (mode == "valid")
        if result.passed:
            assert "bilinmiyor" in result.detail
            assert result.evidence.pid == driver["motor_kaniti"]["pid"]
            assert result.evidence.source_digest == engine.source_digest
            assert result.evidence.persistent_state_unchanged is False
    assert probes[0] != probes[1]
    assert not any(path.exists() for path in probes)


async def test_unsupported_actual_fixture_exits_before_task_without_current_fallback(tmp_path):
    from evals import live_drive

    from .test_live_drive_engine_proof import settings

    args, received = settings(tmp_path)
    args.model_probe = True
    command = live_drive._komut(args)
    assert "evals.driver_engine" in " ".join(command)
    assert command[-1].endswith(",True)")
    result = await live_drive.drive(args, None)
    assert result.get("hata")
    assert not received.exists()
    assert not result["turlar"]


def test_probe_without_selection_cannot_fall_back_to_current_executable():
    import argparse

    from evals import live_drive

    with pytest.raises(ValueError):
        live_drive._komut(argparse.Namespace(log=False, model_probe=True))


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_reaps_term_resistant_owned_grandchild(tmp_path, monkeypatch, cancel):
    import os
    import signal
    import subprocess
    import sys
    import time

    from evals.selected_probe import run_owned_probe

    pidfile = tmp_path / "grandchild.pid"
    child = (
        "import os,signal,time;from pathlib import Path;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);Path("
        + repr(str(pidfile))
        + ").write_text(str(os.getpid()));time.sleep(60)"
    )
    driver = (
        "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"
        + repr(child)
        + "]);time.sleep(60)"
    )
    expected = subprocess.TimeoutExpired
    if cancel:
        import asyncio

        original = subprocess.Popen.communicate
        started = []

        def interrupted(process, *args, **kwargs):
            if not started:
                started.append(True)
                for _ in range(100):
                    if pidfile.exists():
                        break
                    time.sleep(0.01)
                raise asyncio.CancelledError
            return original(process, *args, **kwargs)

        monkeypatch.setattr(subprocess.Popen, "communicate", interrupted)
        expected = asyncio.CancelledError
    with pytest.raises(expected):
        run_owned_probe([sys.executable, "-c", driver], cwd=tmp_path, env={}, timeout=0.3)
    pid = int(pidfile.read_text())
    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.01)
    # Test başarısız olsa bile yalnız kendi fixture sürecini bırakma.
    os.kill(pid, signal.SIGKILL)
    pytest.fail("TERM dirençli fixture torun süreç temizlenmedi.")

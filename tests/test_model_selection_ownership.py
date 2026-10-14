"""Model seçiminde transport iptali thread kilidini erken bırakmaz."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import replace

import pytest

from fusion_cli.appserver.session import AppSession


async def test_cancelled_selection_waiter_cannot_release_commit_or_admission_lock(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "ev")
    entered = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def command(registry, state, name, argument, **kwargs):
        calls.append(argument)
        if argument == "A":
            entered.set()
            assert release.wait(5)
        state.config = replace(state.config, agent=replace(state.config.agent, model=argument))
        return {"ok": True, "metin": "uygulandı"}

    monkeypatch.setattr("fusion_cli.appserver.session.run_command", command)
    waiter = asyncio.create_task(session._run_command({"ad": "development", "arguman": "A"}))
    assert await asyncio.to_thread(entered.wait, 5)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    second = asyncio.create_task(session._run_command({"ad": "development", "arguman": "B"}))
    # Event-loop barrier; süre tahmini olmadan B'nin kilitte beklediğini gözle.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert calls == ["A"]
    assert session._admission_lock.locked()
    release.set()
    result = await second
    assert result["model"] == "B"
    assert session._state.config.agent.model == "B"
    assert not session._model_selection_tasks
    await session.close()


async def test_real_selection_flow_persists_last_serial_intent_and_own_receipt(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml

    from fusion_cli.cli.repl import model_flows
    from fusion_cli.config import writer

    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "ev")
    entered = threading.Event()
    release = threading.Event()

    def probe(model: str):
        if model == "nvidia_nim/A":
            entered.set()
            assert release.wait(5)
        return True, "doğrulandı"

    monkeypatch.setattr(model_flows.catalog, "probe_nim_tools", probe)
    original_write = writer.write_model_section
    path = tmp_path / "selection.yaml"
    monkeypatch.setattr(
        model_flows.writer, "write_model_section", lambda config: original_write(config, path)
    )
    first = asyncio.create_task(
        session._run_command({"ad": "development", "arguman": "uygula nim-free nvidia_nim/A"})
    )
    assert await asyncio.to_thread(entered.wait, 5)
    second = asyncio.create_task(
        session._run_command({"ad": "development", "arguman": "uygula nim-free nvidia_nim/B"})
    )
    await asyncio.sleep(0)
    release.set()
    a, b = await asyncio.gather(first, second)
    assert a["model"] == "nvidia_nim/A"
    assert b["model"] == "nvidia_nim/B"
    assert session._state.config.agent.model == "nvidia_nim/B"
    persisted = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert persisted["agent"]["model"] == "nvidia_nim/B"
    assert persisted["judge"]["model"] == "nvidia_nim/B"
    await session.close()


@pytest.mark.parametrize("role", ["agent", "judge", "cand a"])
async def test_real_model_command_invalid_identity_is_rejected_not_receipted(
    tmp_path, role: str
) -> None:
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "ev")
    original = session._state.config
    if role == "cand a":
        role = f"cand {original.candidates[0].name}"
    result = await session._run_command({"ad": "model", "arguman": f"{role} gecersiz"})
    assert result["ok"] is False
    assert "uygulama" not in result
    assert session._state.config is original
    await session.close()


@pytest.mark.parametrize("route", ["kademe.sec", "kontrol.cirak_varsayilanina_don"])
async def test_model_rpc_waits_for_old_probe_and_its_last_commit_wins(
    tmp_path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    import yaml

    from fusion_cli.appserver import control
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.cli.repl import model_flows
    from fusion_cli.config import writer

    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "ev")
    entered = threading.Event()
    release = threading.Event()
    path = tmp_path / "selection.yaml"
    original_write = writer.write_model_section

    def write(config):
        return original_write(config, path)

    monkeypatch.setattr(model_flows.writer, "write_model_section", write)
    monkeypatch.setattr(control, "write_model_section", write)

    def probe(model: str):
        entered.set()
        assert release.wait(5)
        return True, "doğrulandı"

    monkeypatch.setattr(model_flows.catalog, "probe_nim_tools", probe)
    first = asyncio.create_task(
        session._run_command({"ad": "development", "arguman": "uygula nim-free nvidia_nim/A"})
    )
    assert await asyncio.to_thread(entered.wait, 5)
    data = {"ad": session._state.config.tiers[0].name}
    second = asyncio.create_task(session._dispatch(Request("B", route, data)))
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not second.done(), "Yeni model RPC eski probe bitmeden commit yaptı."
    finally:
        release.set()
        await first
        result = await second
    assert result["ok"] is True
    assert session._state.config.agent.model != "nvidia_nim/A"
    persisted = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert persisted["agent"]["model"] == session._state.config.agent.model
    await session.close()

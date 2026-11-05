"""Desktop /mode auto uses the shared execution profile at the owned turn boundary."""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.config.model_select import apply_tier, select_agent_spec


async def _mode(session, name):
    return await session._dispatch(
        Request(id="mode", name="komut.calistir", data={"ad": "mode", "arguman": name})
    )


def _request(task="Dosya adını değiştir", identifier="job"):
    return Request(
        id=identifier, name="tur.calistir", data={"gorev": task, "gonderim_id": identifier}
    )


def _outcome():
    return SimpleNamespace(ok=True, final_text="bitti", messages=[])


async def test_mode_auto_applies_once_to_executor_and_emits_receipted_reason(tmp_path, monkeypatch):
    lines, configs, choices = [], [], []
    from fusion_cli.engines.agent import auto_profile as classifier

    real_choice = classifier.auto_profile

    def choose(task):
        choices.append(task)
        return real_choice(task)

    async def execute(task, config, **kwargs):
        configs.append(config)
        return _outcome()

    monkeypatch.setattr(classifier, "auto_profile", choose)
    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "ev")
    session._state.config = apply_tier(session._state.config, "high")
    initial = session._state.config
    assert (await _mode(session, "auto"))["ok"]
    request = _request()
    first = await session._dispatch(request)
    replay = await session._dispatch(request)
    assert first["ok"] and replay["ok"]
    assert choices == ["Dosya adını değiştir"]
    assert configs == [apply_tier(initial, "low")]
    assert select_agent_spec(configs[0], "Dosya adını değiştir").model == configs[0].agent.model
    assert session._state.config is configs[0]
    statuses = [
        json.loads(line)["veri"]
        for line in lines
        if "StatusChanged" in line and "görev türü" in line
    ]
    assert len(statuses) == 1
    assert "low" in str(statuses[0])
    assert "job" in str(statuses[0])


@pytest.mark.parametrize("missing_tier", [False, True])
async def test_manual_strict_model_preserved_when_auto_off_or_tier_missing(
    tmp_path, monkeypatch, missing_tier
):
    seen = []

    async def execute(task, config, **kwargs):
        seen.append(config)
        return _outcome()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    original = session._state.config
    manual = replace(original.agent, tags=("strict",))
    session._state.config = replace(
        original, agent=manual, candidates=(manual,), tiers=() if missing_tier else original.tiers
    )
    initial = session._state.config
    if missing_tier:
        await _mode(session, "auto")
    await session._dispatch(_request())
    assert seen == [initial]
    assert seen[0] is initial
    assert session._state.config is initial


async def test_classifier_is_owned_nonblocking_and_cancel_does_not_adopt_late_result(
    tmp_path, monkeypatch
):
    from fusion_cli.engines.agent import auto_profile as classifier

    entered, release = threading.Event(), threading.Event()
    real_choice = classifier.auto_profile
    executed = []

    def choose(task):
        entered.set()
        assert release.wait(5)
        return real_choice(task)

    async def execute(task, config, **kwargs):
        executed.append(task)
        return _outcome()

    monkeypatch.setattr(classifier, "auto_profile", choose)
    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    session._state.config = apply_tier(session._state.config, "high")
    original = session._state.config
    await _mode(session, "auto")
    running = asyncio.create_task(session._dispatch(_request()))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        assert session._turn is not None
        duplicate = await session._dispatch(_request(identifier="other"))
        assert duplicate["ok"] is False
        session._turn.cancel()
        result = await asyncio.wait_for(running, 2)
        assert result["ok"] is False
    finally:
        release.set()
        await asyncio.gather(running, return_exceptions=True)
    assert session._state.config is original
    assert executed == []


async def test_accepted_job_keeps_its_config_and_auto_flag_snapshot(tmp_path, monkeypatch):
    configs = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def execute(task, config, **kwargs):
        configs.append(config)
        return _outcome()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    await _mode(session, "auto")
    initial = session._state.config
    real_finish = session._submission_store.finish

    async def finish(receipt, **kwargs):
        if kwargs.get("state") == "running":
            entered.set()
            await release.wait()
        return await real_finish(receipt, **kwargs)

    monkeypatch.setattr(session._submission_store, "finish", finish)
    running = asyncio.create_task(session._dispatch(_request()))
    await asyncio.wait_for(entered.wait(), 2)
    manual = apply_tier(initial, "high")
    session._state.config = manual
    session._state.auto_profile = False
    release.set()
    assert (await running)["ok"]
    assert configs == [apply_tier(initial, "low")]
    assert session._state.config is manual


async def test_auto_continuation_reuses_selected_config_without_reclassifying(
    tmp_path, monkeypatch
):
    configs, choices = [], []
    from fusion_cli.engines.agent import auto_profile as classifier

    real_choice = classifier.auto_profile

    def choose(task):
        choices.append(task)
        return real_choice(task)

    async def execute(task, config, **kwargs):
        configs.append(config)
        return _outcome()

    monkeypatch.setattr(classifier, "auto_profile", choose)
    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    monkeypatch.setattr(
        "fusion_cli.appserver.session._should_auto_continue", lambda outcome, count: count == 0
    )
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    await _mode(session, "auto")
    assert (await session._dispatch(_request()))["ok"]
    assert choices == ["Dosya adını değiştir"]
    assert len(configs) == 2
    assert configs[0] is configs[1]


async def test_other_session_keeps_manual_model_while_auto_classifier_waits(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import auto_profile as classifier

    entered, release = threading.Event(), threading.Event()
    real_choice = classifier.auto_profile
    seen = {}

    def choose(task):
        entered.set()
        assert release.wait(5)
        return real_choice(task)

    async def execute(task, config, **kwargs):
        seen[task] = config
        return _outcome()

    monkeypatch.setattr(classifier, "auto_profile", choose)
    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    auto = AppSession(lambda line: None, root=tmp_path / "auto", home=tmp_path / "auto-home")
    manual = AppSession(lambda line: None, root=tmp_path / "manual", home=tmp_path / "manual-home")
    manual._state.config = apply_tier(manual._state.config, "high")
    manual_config = manual._state.config
    await _mode(auto, "auto")
    running = asyncio.create_task(auto._dispatch(_request()))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        assert (await asyncio.wait_for(manual._dispatch(_request("manuel görev")), 2))["ok"]
        assert seen["manuel görev"] is manual_config
        assert manual._state.config is manual_config
    finally:
        release.set()
        await running
    assert seen["Dosya adını değiştir"].agent == auto._state.config.tier_by_name("low").agent


async def test_skill_turn_override_remains_above_auto_profile(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.skill_turn import TurnModelChoice

    configs = []

    async def execute(task, config, **kwargs):
        configs.append(config)
        return _outcome()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    await _mode(session, "auto")
    initial = session._state.config
    choice = TurnModelChoice(model="nvidia/skill-model")
    session._state.pending_model_choice = choice
    assert (await session._dispatch(_request()))["ok"]
    assert configs == [choice.apply(apply_tier(initial, "low"))]
    assert session._state.config == apply_tier(initial, "low")


async def test_auto_profile_keeps_disabled_connectors_out_of_turn_config(tmp_path, monkeypatch):
    from fusion_cli.config.models import McpServerConfig

    configs = []

    async def execute(task, config, **kwargs):
        configs.append(config)
        return _outcome()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    servers = (McpServerConfig(name="disabled"), McpServerConfig(name="enabled"))
    session._state.config = replace(session._state.config, mcp_servers=servers)
    session._disabled_mcp.add("disabled")
    await _mode(session, "auto")
    assert (await session._dispatch(_request()))["ok"]
    assert [server.name for server in configs[0].mcp_servers] == ["enabled"]
    assert session._state.config.mcp_servers == servers


async def test_late_profile_result_does_not_update_rebound_visible_chat(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import auto_profile as classifier

    entered, release = threading.Event(), threading.Event()
    real_choice = classifier.auto_profile

    def choose(task):
        entered.set()
        assert release.wait(5)
        return real_choice(task)

    async def execute(task, config, **kwargs):
        return _outcome()

    monkeypatch.setattr(classifier, "auto_profile", choose)
    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    session._state.config = apply_tier(session._state.config, "high")
    original = session._state.config
    await _mode(session, "auto")
    running = asyncio.create_task(session._dispatch(_request()))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        # Conversation binding reuses ReplState and advances this generation.
        session._visible_generation += 1
    finally:
        release.set()
        assert (await running)["ok"]
    assert session._state.config is original


@pytest.mark.parametrize("pause_at", ["running", "claim"])
@pytest.mark.parametrize("rebind", ["none", "conversation", "round_trip", "root"])
async def test_accepted_profile_adoption_uses_admission_chat_binding(
    tmp_path, monkeypatch, rebind, pause_at
):
    configs = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def execute(task, config, **kwargs):
        configs.append(config)
        return _outcome()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    assert (
        await session._dispatch(Request(id="old", name="oturum.baslat", data={"sohbet_id": "old"}))
    )["ok"]
    session._state.config = apply_tier(session._state.config, "high")
    initial = session._state.config
    admission_generation = session._visible_generation
    await _mode(session, "auto")
    real_finish = session._submission_store.finish

    async def finish(receipt, **kwargs):
        if pause_at == "running" and kwargs.get("state") == "running":
            entered.set()
            await release.wait()
        return await real_finish(receipt, **kwargs)

    monkeypatch.setattr(session._submission_store, "finish", finish)
    real_claim = session._submission_store.claim

    async def claim(key):
        result = await real_claim(key)
        if pause_at == "claim":
            entered.set()
            await release.wait()
        return result

    monkeypatch.setattr(session._submission_store, "claim", claim)
    running = asyncio.create_task(session._dispatch(_request()))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert session._turn is None
        if pause_at == "running":
            assert not (await session._dispatch(_request(identifier="other-job")))["ok"]
        if rebind in ("conversation", "round_trip"):
            assert (
                await session._dispatch(
                    Request(id="new", name="oturum.baslat", data={"sohbet_id": "new"})
                )
            )["ok"]
        if rebind == "round_trip":
            assert (
                await session._dispatch(
                    Request(id="back", name="oturum.baslat", data={"sohbet_id": "old"})
                )
            )["ok"]
        if rebind == "root":
            new_root = tmp_path / "new-root"
            new_root.mkdir()
            assert (
                await session._dispatch(
                    Request(id="root", name="oturum.baslat", data={"kok": str(new_root)})
                )
            )["ok"]
        rebound_config = session._state.config
        if rebind != "root":
            assert rebound_config is initial
        assert (session._visible_generation == admission_generation) == (rebind == "none")
    finally:
        release.set()
        result = await running
    assert result["ok"]
    assert result["makbuz"]["oturum_id"] == "old"
    assert configs == [apply_tier(initial, "low")]
    if rebind == "none":
        assert session._state.config is configs[0]
    else:
        assert session._state.config is rebound_config

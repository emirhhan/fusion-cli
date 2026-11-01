"""Ctrl+B: koşan ön plan alt ajanı arka plana alınır, tur beklemeden sürer (#12)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team import SubTask
from fusion_cli.tools.capabilities import CapabilityRegistry
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


def _deps(tmp_path, **launch):
    config = make_config(memory_dir=tmp_path / "bellek")
    if launch:
        config = replace(config, agent_launch=replace(config.agent_launch, **launch))
    return AgentDeps(
        config=config,
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path),
    )


async def test_ctrl_b_on_plan_alt_ajani_arka_plana_alir(tmp_path):
    from fusion_cli.engines.agent.agent_runtime_tools import launch_agent

    deps = _deps(tmp_path)
    started, release = asyncio.Event(), asyncio.Event()

    async def _slow(task, sub_deps, **kwargs):
        started.set()
        await release.wait()
        return SimpleNamespace(final_text="UZUN_IS_BITTI", ok=True, tool_calls_made=0, messages=[])

    call = asyncio.ensure_future(
        launch_agent(
            deps,
            SubTask("uzun iş", persona="general-purpose"),
            {"run_in_background": False},
            depth=0,
            run_agent=_slow,
        )
    )
    await asyncio.wait_for(started.wait(), 10)
    assert deps.child_runs.request_background() is True

    receipt = json.loads((await asyncio.wait_for(call, 10)).output)
    assert receipt["status"] == "async_launched"
    release.set()
    notices = await asyncio.wait_for(
        deps.child_runs.completion_messages(deps.child_runs.session_id), 10
    )
    assert any("UZUN_IS_BITTI" in notice for notice in notices)


def test_arka_plan_kapaliyken_ctrl_b_hicbir_seyi_tasimaz(tmp_path):
    deps = _deps(tmp_path, disable_background_tasks=True)

    assert deps.child_runs.request_background() is False

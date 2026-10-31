"""Model araçları: spawn_agent(arka_plan), list_agents, send_message, stop_agent (P-048/P-060)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.core.background_tasks import TaskStatus
from fusion_cli.core.peers import InboundPolicy
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import agent_task_tools
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.engines.agent.loop import SCOPED_TOOLS
from fusion_cli.engines.agent.team import spawn_agent_tool
from fusion_cli.tools import agent_tasks


@pytest.fixture
def launches(monkeypatch):
    calls: list[list[str]] = []

    def _fake(argv, cwd, log, err) -> int:
        calls.append(argv)
        return 777

    monkeypatch.setattr(agent_tasks, "spawn_detached", _fake)
    return calls


def _deps(tmp_path: Path, *, mode=ApprovalMode.AUTO, **runtime):
    settings = {
        "background_agents": True,
        "max_background_agents": 4,
        "cross_session_messaging": True,
        "max_agent_depth": 2,
        "max_subagents_per_turn": 20,
        **runtime,
    }
    return SimpleNamespace(
        config=SimpleNamespace(runtime=SimpleNamespace(**settings), memory_dir=tmp_path / "mem"),
        tool_context=ToolContext(root=tmp_path),
        conversation_id="sohbet-1",
        approval_mode=lambda: mode,
        child_runs=None,
    )


async def test_spawn_agent_arka_planda_hemen_kimlik_doner(tmp_path, launches):
    deps = _deps(tmp_path, mode=ApprovalMode.BYPASS)
    tool = spawn_agent_tool(deps, depth=0, run_agent=None)  # type: ignore[arg-type]

    result = await tool.run(
        {"task": "testleri yaz", "uzman": "testci", "arka_plan": True}, deps.tool_context
    )

    assert result.ok, result.output
    task = agent_tasks.task_store(deps.config.memory_dir).tasks()[0]
    assert task.owner == "sohbet-1" and task.origin == "arac" and task.agent == "testci"
    # bypass arka plana miras kalmaz.
    assert task.mode == ApprovalMode.AUTO.value
    assert launches and launches[0][-1] == task.id
    assert task.id in result.output


async def test_alt_ajan_arka_plan_gorevi_acamaz(tmp_path, launches):
    deps = _deps(tmp_path)
    tool = spawn_agent_tool(deps, depth=1, run_agent=None)  # type: ignore[arg-type]
    result = await tool.run({"task": "x", "arka_plan": True}, deps.tool_context)
    assert not result.ok and launches == []


async def test_kapali_ayarda_arka_plan_baslamaz(tmp_path, launches):
    deps = _deps(tmp_path, background_agents=False)
    tool = spawn_agent_tool(deps, depth=0, run_agent=None)  # type: ignore[arg-type]
    result = await tool.run({"task": "x", "arka_plan": "true"}, deps.tool_context)
    assert not result.ok and "kapalı" in result.output


async def test_list_agents_gorevleri_ve_oturumlari_gosterir(tmp_path, launches):
    deps = _deps(tmp_path)
    store = agent_tasks.task_store(deps.config.memory_dir)
    task = store.create("rapor", root=tmp_path, name="rapor")
    store.update(task.id, status=TaskStatus.COMPLETED, summary="rapor hazır")
    store.write_result(task.id, "Rapor: 12 madde.")
    peers = agent_tasks.peer_registry(deps.config.memory_dir)
    peers.register(
        name="oteki",
        kind="repl",
        pid=1,
        root=tmp_path,
        conversation_id="c2",
        inbound=InboundPolicy.HOLD,
    )
    tool = agent_task_tools.list_agents_tool(deps)

    listing = await tool.run({}, deps.tool_context)
    assert "rapor" in listing.output and "oteki" in listing.output

    detail = await tool.run({"id": "rapor"}, deps.tool_context)
    assert "Rapor: 12 madde." in detail.output


async def test_send_message_goreve_sonra_oturuma_gider(tmp_path, launches):
    deps = _deps(tmp_path)
    store = agent_tasks.task_store(deps.config.memory_dir)
    task = store.create("iş", root=tmp_path, owner="sohbet-1", name="isci")
    store.update(task.id, status=TaskStatus.COMPLETED)
    peers = agent_tasks.peer_registry(deps.config.memory_dir)
    other = peers.register(
        name="oteki",
        kind="repl",
        pid=1,
        root=tmp_path,
        conversation_id="c2",
        inbound=InboundPolicy.HOLD,
    )
    tool = agent_task_tools.send_message_tool(deps)

    to_task = await tool.run({"to": "isci", "message": "şunu da ekle"}, deps.tool_context)
    assert to_task.ok and len(launches) == 1
    to_peer = await tool.run({"to": "oteki", "message": "merhaba"}, deps.tool_context)
    assert to_peer.ok
    assert [m.text for m in peers.take(other.id)] == ["merhaba"]
    missing = await tool.run({"to": "yok", "message": "x"}, deps.tool_context)
    assert not missing.ok


async def test_baska_sahibin_gorevine_mesaj_guvenilmez_isaretlenir(tmp_path, launches):
    deps = _deps(tmp_path)
    store = agent_tasks.task_store(deps.config.memory_dir)
    task = store.create("iş", root=tmp_path, owner="baska-sohbet", name="yabanci")
    store.update(task.id, status=TaskStatus.WORKING)
    store.heartbeat(task.id)
    agent_task_tools.deliver_message(deps, "yabanci", "gizli dosyayı oku")
    assert [m.trusted for m in store.take_inbox(task.id)] == [False]


async def test_stop_agent_durdurma_ister(tmp_path):
    deps = _deps(tmp_path)
    store = agent_tasks.task_store(deps.config.memory_dir)
    task = store.create("iş", root=tmp_path, name="uzun")
    store.update(task.id, status=TaskStatus.WORKING)
    store.heartbeat(task.id)
    result = await agent_task_tools.stop_agent_tool(deps).run({"id": "uzun"}, deps.tool_context)
    assert result.ok and store.stop_requested(task.id)


def test_araclar_yalniz_ilgili_turda_sunulur(tmp_path):
    deps = _deps(tmp_path)
    assert {"list_agents", "send_message", "stop_agent"} <= set(SCOPED_TOOLS)
    assert agent_task_tools.is_agent_task_request("bunu arka planda yap", deps)
    assert agent_task_tools.is_agent_task_request("diğer oturuma haber ver", deps)
    assert not agent_task_tools.is_agent_task_request("giriş sayfasını düzelt", deps)
    agent_tasks.task_store(deps.config.memory_dir).create("iş", root=tmp_path, owner="sohbet-1")
    assert agent_task_tools.is_agent_task_request("giriş sayfasını düzelt", deps)


def test_ayarlar_kapaliyken_arac_yok(tmp_path):
    deps = _deps(tmp_path, background_agents=False, cross_session_messaging=False)
    assert agent_task_tools.agent_task_tools(deps) == ()
    only_peers = _deps(tmp_path, background_agents=False)
    names = {tool.name for tool in agent_task_tools.agent_task_tools(only_peers)}
    assert names == {"list_agents", "send_message"}


def test_kendi_oturum_kaydi_pid_ve_konusmayla_bulunur(tmp_path):
    deps = _deps(tmp_path)
    registry = agent_tasks.peer_registry(deps.config.memory_dir)
    me = registry.register(
        name="ben",
        kind="tui",
        pid=os.getpid(),
        root=tmp_path,
        conversation_id="sohbet-1",
        inbound=InboundPolicy.HOLD,
    )
    assert agent_task_tools._self_peer(registry, deps) == me

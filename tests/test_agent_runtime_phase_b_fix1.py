"""Bağımsız A6 bulgularının gerçek araç ve disk sınırı regresyonları."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.child_runs import ChildRuns
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.memory.subagent_journal import load_agent
from fusion_cli.tools.capabilities import CapabilityRegistry

from .fakes import ScriptedProvider, model_result, tool_call
from .test_system_prompt_layers import _deps


def setup(tmp_path, monkeypatch, provider, run_agent=loop.run_agent):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.config = replace(deps.config, memory_dir=tmp_path / "memory")
    deps.conversation_id = "fix1-oturum"
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", tmp_path)
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    return deps, build_agent_registry(deps, depth=0, run_agent=run_agent)


@pytest.mark.parametrize("mode", ["inherited", "empty", "request", "parent", "disjoint"])
async def test_disk_resume_intersects_all_effective_write_limits(monkeypatch, tmp_path, mode):
    allowed = tmp_path / "allowed"
    narrow = allowed / "narrow"
    narrow.mkdir(parents=True)
    scopes = []

    async def observed(task, child, **kwargs):
        scopes.append(child.tool_context.write_scope)
        return await loop.run_agent(task, child, **kwargs)

    blocked = "allowed/outside.txt" if mode in {"request", "parent"} else "outside.txt"
    provider = ScriptedProvider(
        [
            model_result("İlk sonuç"),
            model_result(tool_calls=(tool_call("write_file", path=blocked, content="yasak"),)),
            model_result("Devam sonucu"),
        ]
    )
    deps, registry = setup(tmp_path, monkeypatch, provider, observed)
    deps.tool_context = replace(
        deps.tool_context, write_scope=() if mode == "empty" else (allowed,)
    )
    first = await registry.get("Agent").run(
        {"prompt": "Başla", "run_in_background": False}, deps.tool_context
    )
    assert first.ok, first.output
    identifier = json.loads(first.output)["agentId"]
    saved = load_agent(deps.config.memory_dir, tmp_path, deps.conversation_id, identifier)
    assert saved.agent_state.write_scope == (() if mode == "empty" else (str(allowed),))
    deps.child_runs = ChildRuns()
    current = (narrow,) if mode == "parent" else None
    deps.tool_context = replace(deps.tool_context, write_scope=current)
    args = {"prompt": "Devam", "resume": identifier, "run_in_background": False}
    if mode in {"request", "disjoint"}:
        args["yazma_alani"] = ["allowed/narrow" if mode == "request" else "elsewhere"]
    resumed = await registry.get("Agent").run(args, deps.tool_context)
    assert resumed.ok, resumed.output
    expected = (
        ()
        if mode in {"empty", "disjoint"}
        else (narrow,)
        if mode in {"parent", "request"}
        else (allowed,)
    )
    assert scopes[-1] == expected
    assert not (tmp_path / blocked).exists()


@pytest.mark.parametrize("tool_arguments", [False, True])
async def test_redaction_marks_receipt_disk_and_resumed_history_incomplete(
    monkeypatch, tmp_path, tool_arguments
):
    contact = "demo@example.invalid"
    replies = [model_result(contact), model_result("Devam")]
    if tool_arguments:
        replies = [
            model_result(tool_calls=(tool_call("read_file", path=contact),)),
            model_result("Bitti"),
            model_result("Devam"),
        ]
    provider = ScriptedProvider(replies)
    deps, registry = setup(tmp_path, monkeypatch, provider)
    first = await registry.get("Agent").run(
        {"prompt": "Hatırla", "run_in_background": False}, deps.tool_context
    )
    receipt = json.loads(first.output)
    assert receipt["completeHistory"] is False
    identifier = receipt["agentId"]
    assert deps.child_runs.record(identifier).complete_history is False
    saved = load_agent(deps.config.memory_dir, tmp_path, deps.conversation_id, identifier)
    assert saved.agent_state.complete_history is False
    assert contact not in await asyncio.to_thread(Path(receipt["transcriptPath"]).read_text)
    deps.child_runs = ChildRuns()
    resumed = await registry.get("Agent").run(
        {"prompt": "Devam", "resume": identifier, "run_in_background": False}, deps.tool_context
    )
    assert resumed.ok and not json.loads(resumed.output)["completeHistory"]
    assert any(
        "eksiksiz özgün geçmiş değildir" in msg.content for msg in provider.seen_messages[-1]
    )


@pytest.mark.parametrize(
    "name,args",
    [
        ("Agent", {"subagent_type": "missing-reviewer"}),
        ("spawn_agent", {"uzman": "missing-reviewer"}),
    ],
)
async def test_unknown_allowlisted_type_never_runs_generic_provider(
    monkeypatch, tmp_path, name, args
):
    provider = ScriptedProvider([model_result("Yanlış genel ajan")])
    deps, registry = setup(tmp_path, monkeypatch, provider)
    deps.allowed_agent_types = ("missing-reviewer",)
    result = await registry.get(name).run(
        {"task": "Oku", "prompt": "Oku", "run_in_background": False, **args}, deps.tool_context
    )
    assert not result.ok
    assert provider.calls == 0
    assert not deps.child_runs.records()


@pytest.mark.parametrize("target", ["", "   ", None, 42, "yanlis-kimlik"])
async def test_invalid_stop_never_cancels_unnamed_running_child(monkeypatch, tmp_path, target):
    entered = asyncio.Event()

    class Waiting(ScriptedProvider):
        async def stream(self, request):
            entered.set()
            await asyncio.Event().wait()
            async for event in super().stream(request):
                yield event

    deps, registry = setup(tmp_path, monkeypatch, Waiting([]))
    try:
        first = await registry.get("Agent").run(
            {"prompt": "Bekle", "run_in_background": True}, deps.tool_context
        )
        identifier = json.loads(first.output)["agentId"]
        await asyncio.wait_for(entered.wait(), 3)
        result = await registry.get("TaskStop").run({"task_id": target}, deps.tool_context)
        assert not result.ok
        assert deps.child_runs.running(identifier)
        valid = await registry.get("TaskStop").run({"task_id": identifier}, deps.tool_context)
        assert valid.ok and not deps.child_runs.running(identifier)
    finally:
        await deps.child_runs.close()


@pytest.mark.parametrize("session", ["fix1-oturum", ""])
async def test_actual_child_sendmessage_delivers_sibling_but_rejects_foreign(
    monkeypatch, tmp_path, session
):
    entered = asyncio.Event()
    children = []

    class Waiting(ScriptedProvider):
        async def stream(self, request):
            entered.set()
            await asyncio.Event().wait()
            async for event in super().stream(request):
                yield event

    async def observed(task, child, **kwargs):
        children.append(child)
        return await loop.run_agent(task, child, **kwargs)

    deps, registry = setup(tmp_path, monkeypatch, Waiting([]), observed)
    deps.conversation_id = session
    try:
        started = await registry.get("Agent").run(
            {"prompt": "Bekle", "name": "kardes", "run_in_background": True}, deps.tool_context
        )
        sibling = json.loads(started.output)["agentId"]
        await asyncio.wait_for(entered.wait(), 3)
        monkeypatch.setattr(
            loop, "build_provider", lambda *a, **k: ScriptedProvider([model_result("Gönderici")])
        )
        sender = await registry.get("Agent").run(
            {"prompt": "Gönder", "run_in_background": False}, deps.tool_context
        )
        assert sender.ok
        child = children[-1]
        child_registry = build_agent_registry(child, depth=1, run_agent=loop.run_agent)
        delivered = await child_registry.get("SendMessage").run(
            {"to": sibling, "message": "KARDEŞ-KANIT"}, child.tool_context
        )
        assert delivered.ok, delivered.output
        assert "KARDEŞ-KANIT" in deps.child_runs.message_queue(sibling).drain()[0].content
        state = deps.child_runs.record(sibling)
        for foreign in (
            replace(state, parent_session="yabanci"),
            replace(state, root=str(tmp_path / "yabanci")),
        ):
            deps.child_runs.remember(foreign, ())
            denied = await child_registry.get("SendMessage").run(
                {"to": sibling, "message": "YASAK"}, child.tool_context
            )
            assert not denied.ok
            assert not deps.child_runs.message_queue(sibling).drain()
        deps.child_runs.remember(state, ())
        await assert_sibling_control_boundaries(child, child_registry, sibling)
    finally:
        await deps.child_runs.close()


async def test_legacy_unproven_scope_is_rejected_before_provider(monkeypatch, tmp_path):
    provider = ScriptedProvider([model_result("İlk sonuç")])
    deps, registry = setup(tmp_path, monkeypatch, provider)
    first = await registry.get("Agent").run(
        {"prompt": "Başla", "run_in_background": False}, deps.tool_context
    )
    receipt = json.loads(first.output)
    path = Path(receipt["transcriptPath"])
    raw = json.loads(await asyncio.to_thread(path.read_text))
    raw["ajan"].pop("effective_write_scope")
    await asyncio.to_thread(path.write_text, json.dumps(raw))
    deps.child_runs = ChildRuns()
    resumed = await registry.get("Agent").run(
        {"prompt": "Devam", "resume": receipt["agentId"], "run_in_background": False},
        deps.tool_context,
    )
    assert not resumed.ok and provider.calls == 1


@pytest.mark.parametrize("tool", ["Agent", "SendMessage"])
async def test_removed_definition_on_disk_resume_never_runs_generic(monkeypatch, tmp_path, tool):
    from fusion_cli.tools.capabilities import Capability

    provider = ScriptedProvider([model_result("Özel sonuç")])
    deps, registry = setup(tmp_path, monkeypatch, provider)
    agent = Capability(
        "ozel", "Özel tanım", tmp_path / "ozel.md", "cli", inline_prompt="Yalnız oku"
    )
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", tmp_path, session_agents=(agent,))
    deps.allowed_agent_types = ("ozel",)
    first = await registry.get("Agent").run(
        {"prompt": "Başla", "subagent_type": "ozel", "run_in_background": False}, deps.tool_context
    )
    identifier = json.loads(first.output)["agentId"]
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", tmp_path)
    deps.child_runs = ChildRuns()
    args = (
        {"to": identifier, "message": "Devam"}
        if tool == "SendMessage"
        else {"resume": identifier, "prompt": "Devam", "run_in_background": False}
    )
    resumed = await registry.get(tool).run(args, deps.tool_context)
    assert not resumed.ok and provider.calls == 1


@pytest.mark.parametrize("own_child", [False, True])
async def test_child_resumes_completed_sibling_in_original_owner_scope(
    monkeypatch, tmp_path, own_child
):
    children = []

    async def observed(task, child, **kwargs):
        children.append(child)
        return await loop.run_agent(task, child, **kwargs)

    provider = ScriptedProvider(
        [
            model_result("Kardeş"),
            model_result("Gönderen"),
            model_result("Devam"),
            model_result("Son"),
        ]
    )
    deps, registry = setup(tmp_path, monkeypatch, provider, observed)
    first = await registry.get("Agent").run(
        {"prompt": "Başla", "name": "kardes", "run_in_background": False}, deps.tool_context
    )
    identifier = json.loads(first.output)["agentId"]
    await registry.get("Agent").run(
        {"prompt": "Gönder", "run_in_background": False}, deps.tool_context
    )
    sender = children[-1]
    child_registry = build_agent_registry(sender, depth=1, run_agent=loop.run_agent)
    if own_child:
        nested = await child_registry.get("Agent").run(
            {"prompt": "İç görev", "run_in_background": False}, sender.tool_context
        )
        identifier = json.loads(nested.output)["agentId"]
    result = await child_registry.get("SendMessage").run(
        {"to": identifier, "message": "Devam"}, sender.tool_context
    )
    assert result.ok, result.output
    await deps.child_runs.drain()
    state = deps.child_runs.record(identifier)
    assert state.parent_session == (sender.conversation_id if own_child else deps.conversation_id)
    assert state.status == "completed"
    assert provider.calls == (4 if own_child else 3)
    assert await asyncio.to_thread(Path(json.loads(result.output)["transcriptPath"]).is_file)


async def test_invalid_initial_scope_returns_failure_before_provider(monkeypatch, tmp_path):
    provider = ScriptedProvider([])
    deps, registry = setup(tmp_path, monkeypatch, provider)
    deps.tool_context = replace(deps.tool_context, write_scope=())
    result = await registry.get("Agent").run(
        {"prompt": "Başla", "yazma_alani": ["outside"], "run_in_background": False},
        deps.tool_context,
    )
    assert not result.ok and provider.calls == 0


@pytest.mark.parametrize("agent_type", ["general-purpose", "yardimci", "Explore", "fork"])
async def test_explicit_generic_builtin_and_defined_fork_remain_available(
    monkeypatch, tmp_path, agent_type
):
    provider = ScriptedProvider([model_result("Tamam")])
    deps, registry = setup(tmp_path, monkeypatch, provider)
    deps.config = replace(
        deps.config, agent_launch=replace(deps.config.agent_launch, fork_enabled=True)
    )
    deps.allowed_agent_types = (agent_type,)
    result = await registry.get("Agent").run(
        {"prompt": "Başla", "subagent_type": agent_type, "run_in_background": False},
        deps.tool_context,
    )
    assert result.ok, result.output
    assert provider.calls == 1


async def assert_sibling_control_boundaries(child, registry, sibling):
    """Mesaj kapsamı durdurma/devam sahipliğini veya tür iznini genişletmez."""
    stopped = await registry.get("TaskStop").run({"task_id": sibling}, child.tool_context)
    assert not stopped.ok and child.child_runs.running(sibling)
    resumed = await registry.get("Agent").run(
        {"resume": sibling, "prompt": "YASAK", "run_in_background": False}, child.tool_context
    )
    assert not resumed.ok
    child.allowed_agent_types = ()
    denied = await registry.get("SendMessage").run(
        {"to": sibling, "message": "YASAK"}, child.tool_context
    )
    assert not denied.ok and not child.child_runs.message_queue(sibling).drain()
    child.allowed_agent_types = None

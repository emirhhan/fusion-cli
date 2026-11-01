"""Alt ajan kimliği ve bilinen tam geçmişle devam sınırları."""

from __future__ import annotations

import json

from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.engine_tools import build_agent_registry

from .fakes import ScriptedProvider, model_result
from .test_system_prompt_layers import _deps


async def test_agent_sendmessage_resume_keeps_known_history_and_id(monkeypatch, tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.conversation_id = "ana-oturum"
    provider = ScriptedProvider([model_result("İlk kanıt 731."), model_result("İkinci kanıt 732.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    first = await registry.get("Agent").run(
        {"prompt": "İlk görev", "run_in_background": False}, deps.tool_context
    )
    result = json.loads(first.output)
    identifier = result["agentId"]
    assert identifier
    resume = registry.get("SendMessage")
    assert resume is not None
    continued = await resume.run({"to": identifier, "message": "Devam"}, deps.tool_context)
    assert continued.ok
    await deps.child_runs.drain()
    assert any(message.content == "İlk görev" for message in provider.seen_messages[-1])
    assert any(message.content == "İlk kanıt 731." for message in provider.seen_messages[-1])
    assert deps.child_runs.record(identifier).agent_id == identifier


async def test_background_agent_is_owned_and_drain_observes_completion(monkeypatch, tmp_path):
    from fusion_cli.core.tools import ToolResult

    async def no_process(*args, **kwargs):
        return ToolResult.failure("Eski ayrı süreç yolu testte kapalı.")

    blocked = []

    def forbidden(*args, **kwargs):
        blocked.append(True)
        raise AssertionError("Ayrı süreç veya gerçek sağlayıcı yasak.")

    monkeypatch.setattr("fusion_cli.engines.agent.agent_task_tools.spawn_background", no_process)
    monkeypatch.setattr("fusion_cli.tools.agent_tasks.spawn_detached", forbidden)
    monkeypatch.setattr("fusion_cli.tools.agent_tasks.start_with_settings", forbidden)
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", forbidden)
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    provider = ScriptedProvider([model_result("Arka görev bitti.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    result = await registry.get("Agent").run(
        {"prompt": "Merhaba", "run_in_background": True}, deps.tool_context
    )
    assert result.ok, result.output
    receipt = json.loads(result.output)
    assert receipt["status"] == "async_launched"
    await deps.child_runs.drain()
    assert deps.child_runs.record(receipt["agentId"]).status == "completed"

    assert blocked == []


async def test_disk_resume_preserves_large_precompaction_history(monkeypatch, tmp_path):
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent.child_runs import ChildRuns

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.conversation_id = "kalici-oturum"
    original = "SAKLANACAK-KANIT-" + "k" * 70000
    provider = ScriptedProvider([model_result(original), model_result("Devam tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)

    async def compact(messages, deps, threshold, **kwargs):
        return [
            messages[0],
            Message("user", "Yalnız özet", harness_note=True),
            Message("assistant", "Kısa sonuç"),
        ]

    monkeypatch.setattr(loop, "compact_context", compact)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    first = await registry.get("Agent").run(
        {"prompt": "ORIGINAL-GÖREV-7942", "run_in_background": False}, deps.tool_context
    )
    receipt = json.loads(first.output)
    assert receipt["completeHistory"] is True
    deps.child_runs = ChildRuns()
    resumed = await registry.get("Agent").run(
        {"prompt": "Devam", "resume": receipt["agentId"], "run_in_background": False},
        deps.tool_context,
    )
    assert resumed.ok, resumed.output
    assert any(message.content == original for message in provider.seen_messages[-1])
    assert any(message.content == "ORIGINAL-GÖREV-7942" for message in provider.seen_messages[-1])
    assert json.loads(resumed.output)["agentId"] == receipt["agentId"]


async def test_resume_honors_saved_read_only_and_current_type_scope(monkeypatch, tmp_path):
    from fusion_cli.engines.agent.child_runs import ChildRuns

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.conversation_id = "sinirli"
    provider = ScriptedProvider([model_result("Kanıt.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    result = await registry.get("Agent").run(
        {"prompt": "Oku", "salt_okunur": True, "run_in_background": False}, deps.tool_context
    )
    identifier = json.loads(result.output)["agentId"]
    assert deps.child_runs.record(identifier).read_only is True
    deps.child_runs = ChildRuns()
    deps.allowed_agent_types = ()
    denied = await registry.get("SendMessage").run(
        {"to": identifier, "message": "Yaz"}, deps.tool_context
    )
    assert not denied.ok
    assert deps.child_runs.record(identifier).read_only is True
    assert len(provider.seen_messages) == 1


async def test_parent_observes_background_completion_before_final_answer(monkeypatch, tmp_path):
    from .fakes import tool_call

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    parent = ScriptedProvider(
        [
            model_result(
                tool_calls=(tool_call("Agent", prompt="Kanıtı bul", description="Kanıt"),)
            ),
            model_result("Ajan bekleniyor."),
            model_result("Kanıt 8247 bulundu."),
        ]
    )
    child = ScriptedProvider([model_result("SONUÇ-8247")])
    from fusion_cli.core.events import Channel

    monkeypatch.setattr(
        loop,
        "build_provider",
        lambda *args, **kwargs: child if kwargs.get("channel") is Channel.SUBAGENT else parent,
    )
    outcome = await loop.run_agent("Bir yardımcı kullanarak kanıtı bul", deps)
    assert outcome.ok, outcome.final_text
    assert any("SONUÇ-8247" in message.content for message in parent.seen_messages[-1])
    assert not deps.child_runs._background


async def test_legacy_controls_reach_same_background_owner(monkeypatch, tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    provider = ScriptedProvider([model_result("Yerel sonuç.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    started = await registry.get("spawn_agent").run(
        {"task": "Merhaba", "arka_plan": True}, deps.tool_context
    )
    assert started.ok
    await deps.child_runs.drain()
    identifier = deps.child_runs.records()[0].agent_id
    status = await registry.get("list_agents").run({"id": identifier}, deps.tool_context)
    assert status.ok and "Yerel sonuç." in status.output


async def test_persistent_child_survives_turn_and_closed_bus_then_reaches_next_turn(
    monkeypatch, tmp_path
):
    import asyncio
    from dataclasses import replace

    from fusion_cli.core.events import Channel, SubAgentFinished
    from fusion_cli.engines.agent.child_runs import ChildRuns
    from fusion_cli.observability.bus import EventBus

    from .fakes import RecordingSink, tool_call

    entered, release = asyncio.Event(), asyncio.Event()

    class DelayedProvider(ScriptedProvider):
        async def stream(self, request):
            entered.set()
            await release.wait()
            async for item in super().stream(request):
                yield item

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.conversation_id = "kalici-ana"
    deps.child_runs = ChildRuns(persistent=True)
    parent = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("Agent", prompt="Kanıtı bul"),)),
            model_result("Ajan sürüyor."),
            model_result("Kanıt hazır."),
        ]
    )
    child = DelayedProvider([model_result("GEÇ-SONUÇ-9473")])
    monkeypatch.setattr(
        loop,
        "build_provider",
        lambda *args, **kwargs: child if kwargs.get("channel") is Channel.SUBAGENT else parent,
    )
    sink = RecordingSink()
    bus = EventBus()
    async with bus:
        bus.subscribe(sink)
        deps.publisher = bus
        first = await loop.run_agent("Yardımcı başlat", deps)
        await asyncio.wait_for(entered.wait(), 2)
        identifier = deps.child_runs.records()[0].agent_id
        original_turn = deps.child_runs.turn_for(identifier)
        assert original_turn and deps.child_runs.running(identifier)
    release.set()
    await deps.child_runs.drain()
    finished = [event for event in sink.events if isinstance(event, SubAgentFinished)]
    assert finished and finished[-1].turn_id == original_turn and not bus.failures
    next_turn = replace(deps, budget=None)
    await loop.run_agent("Sonuç ne?", next_turn, history=first.messages)
    assert any("GEÇ-SONUÇ-9473" in message.content for message in parent.seen_messages[-1])
    await deps.child_runs.close()


async def test_persistent_cancellation_and_budget_are_scoped_to_real_turn(tmp_path):
    import asyncio

    from fusion_cli.core.agent_runtime_state import AgentRunState
    from fusion_cli.engines.agent.child_runs import ChildRuns

    owner = ChildRuns(persistent=True)
    cancelled = []

    async def waiting(identifier):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(identifier)

    for identifier, turn in (("ajan-1", "tur-1"), ("ajan-2", "tur-2")):
        owner.remember(
            AgentRunState(
                identifier,
                "oturum",
                str(tmp_path),
                "yardimci",
                False,
                status="running",
                parent_turn=turn,
            ),
            (),
        )
        owner.launch(identifier, waiting(identifier))
    await asyncio.sleep(0)
    await owner.cancel_turn("")
    assert owner.running("ajan-1") and owner.running("ajan-2")
    await owner.cancel_turn("tur-2")
    assert owner.running("ajan-1") and not owner.running("ajan-2")
    assert owner.record("ajan-2").status == "cancelled"
    await owner.close()
    assert sorted(cancelled) == ["ajan-1", "ajan-2"]


async def test_legacy_status_restores_owned_durable_agent(monkeypatch, tmp_path):
    from fusion_cli.engines.agent.child_runs import ChildRuns

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.conversation_id = "kalici-eski-arac"
    provider = ScriptedProvider([model_result("KALICI-SONUÇ-3821")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    first = await registry.get("Agent").run(
        {"prompt": "Kanıtı sakla", "run_in_background": False}, deps.tool_context
    )
    identifier = json.loads(first.output)["agentId"]
    deps.child_runs = ChildRuns()
    restored = await registry.get("list_agents").run({"id": identifier}, deps.tool_context)
    assert restored.ok and "KALICI-SONUÇ-3821" in restored.output


async def test_persistent_budget_counts_each_originating_turn():
    import asyncio

    from fusion_cli.engines.agent.child_runs import ChildRuns

    owner = ChildRuns(persistent=True)
    first = owner.begin_turn("ilk")
    release = asyncio.Event()

    async def old_work():
        await release.wait()
        nested = owner.start("eski-alt", lambda: asyncio.sleep(0))
        await nested
        assert owner.started_for_current_turn == 2
        owner.detach("eski-alt", nested)

    old = owner.start("eski", old_work)
    owner.end_turn(first)
    second = owner.begin_turn("ikinci")
    assert owner.started_for_current_turn == 0
    new = owner.start("yeni", lambda: asyncio.sleep(0))
    await new
    assert owner.started_for_current_turn == 1
    release.set()
    await old
    assert owner.started_for_current_turn == 1
    owner.detach("eski", old)
    owner.detach("yeni", new)
    owner.end_turn(second)
    await owner.close()


async def test_completed_receipt_points_to_existing_scoped_transcript(monkeypatch, tmp_path):
    import asyncio
    from pathlib import Path

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    provider = ScriptedProvider([model_result("Kayıtlı sonuç")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    result = await registry.get("Agent").run(
        {"prompt": "Kayıt tut", "run_in_background": False}, deps.tool_context
    )
    receipt = json.loads(result.output)
    path = Path(receipt["transcriptPath"])
    assert await asyncio.to_thread(path.is_file)
    assert path.is_relative_to(deps.config.memory_dir.resolve())
    assert "Kayıtlı sonuç" in await asyncio.to_thread(path.read_text)

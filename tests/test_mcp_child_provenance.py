"""Descendant MCP metadata remains untrusted at the parent's learning boundary."""

import asyncio
from dataclasses import replace

import pytest

from fusion_cli.config.models import McpServerConfig
from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.tools import Tool, ToolResult
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import loop, team
from fusion_cli.mcp_bridge.discovery import McpDiscovery
from tests.test_system_prompt_layers import _deps


@pytest.mark.parametrize("exit_kind", ["success", "error", "cancel", "nested", "parent_true"])
async def test_real_child_discovery_preserves_external_taint_through_every_exit(
    tmp_path, monkeypatch, exit_kind
):
    from fusion_cli.mcp_bridge import pool

    parent = _deps(tmp_path, "nvidia_nim/synthetic")
    parent.config = replace(
        parent.config, mcp_servers=(McpServerConfig("opaque", command="never-start"),)
    )
    owner = McpDiscovery(lambda: parent.config, root=tmp_path)
    parent.mcp_discovery = owner
    parent.mcp_external_content = exit_kind == "parent_true"
    selected = []

    async def ensure(configs, registry, **kwargs):
        selected.append(kwargs["selected_names"])
        registry.register_or_replace(
            Tool(
                "mcp__opaque__read",
                "Untrusted server-authored metadata",
                {},
                lambda a, c: ToolResult(output="unused"),
            )
        )
        return ("mcp__opaque__read",)

    monkeypatch.setattr(pool, "ensure_mcp_tools", ensure)

    async def child_runner(task, child, **kwargs):
        if exit_kind == "nested" and kwargs["depth"] == 1:
            return await team._run_child(
                child,
                team.SubTask("Inspect nested metadata"),
                team.GENERIC_PERSONA,
                "nested-child",
                1,
                child_runner,
                child.tool_context,
            )
        if exit_kind == "parent_true":
            child.mcp_external_content = False
        else:
            discovery = child.mcp_discovery.bind(
                child.base_registry,
                permitted=lambda: set(child.base_registry.names()),
                admit=lambda _: True,
                deps=child,
            )
            result = await discovery.run({"server": "opaque"}, child.tool_context)
            assert result.ok and child.mcp_external_content
        if exit_kind == "error":
            raise RuntimeError("synthetic child failure")
        if exit_kind == "cancel":
            raise asyncio.CancelledError()
        return loop.AgentOutcome(
            final_text="Server-authored usage relayed to parent.",
            messages=[Message("assistant", "Untrusted metadata result")],
            ok=True,
        )

    try:
        if exit_kind in {"error", "cancel"}:
            with pytest.raises(RuntimeError if exit_kind == "error" else asyncio.CancelledError):
                await team._run_child(
                    parent,
                    team.SubTask("Inspect metadata"),
                    team.GENERIC_PERSONA,
                    "child",
                    0,
                    child_runner,
                    parent.tool_context,
                )
        else:
            result = await team._run_child(
                parent,
                team.SubTask("Inspect metadata"),
                team.GENERIC_PERSONA,
                "child",
                0,
                child_runner,
                parent.tool_context,
            )
            assert result.ok
        assert parent.mcp_external_content
        assert selected == ([] if exit_kind == "parent_true" else [frozenset({"opaque"})])
        if exit_kind in {"success", "nested"}:
            from tests import test_external_lessons as fixture

            memory = fixture._Bellek()

            def actual_parent(bellek, events, guven):
                parent.lessons = bellek
                parent.config = replace(
                    parent.config,
                    runtime=replace(
                        parent.config.runtime, lessons=True, external_lesson_confidence=guven
                    ),
                )
                return parent

            monkeypatch.setattr(fixture, "_deps", actual_parent)
            await fixture._ogren(
                monkeypatch, memory, kullanimlar=[ToolUse("Agent"), ToolUse("read_file")], guven=0.4
            )
            assert memory.eklenen and all(lesson.external for lesson in memory.eklenen)
            assert all(lesson.confidence <= 0.4 for lesson in memory.eklenen)
    finally:
        owner.close()


async def test_persisted_resumed_child_history_is_consumed_as_unverified(tmp_path, monkeypatch):
    from fusion_cli.core.agent_runtime_state import AgentRunState
    from fusion_cli.engines.agent.agent_runtime_records import _resume_task
    from fusion_cli.memory.subagent_journal import agent_journal

    parent = _deps(tmp_path, "nvidia_nim/synthetic")
    parent.conversation_id = "parent-session"
    state = AgentRunState("saved", "parent-session", str(tmp_path.resolve()), "general", True)
    agent_journal(parent.config.memory_dir, tmp_path, "parent-session", "saved", state=state).save(
        [Message("assistant", "Opaque persisted server-authored summary")]
    )
    from fusion_cli.engines.agent.agent_runtime_tools import _list_agents

    receipt = await _list_agents({"id": "saved"}, parent.tool_context, deps=parent)
    assert receipt.ok and "Opaque persisted" in receipt.output
    assert parent.mcp_external_content
    # A fresh consuming turn must also taint when resuming, without relying on
    # the prior receipt's in-memory flag.
    parent.mcp_external_content = False
    resumed = await _resume_task(parent, team.SubTask("Use saved summary", resume="saved"))

    async def child_runner(task, child, **kwargs):
        assert child.mcp_external_content
        return loop.AgentOutcome(final_text="Persisted summary relayed.", messages=[], ok=True)

    result = await team._run_child(
        parent, resumed, team.GENERIC_PERSONA, "saved", 0, child_runner, parent.tool_context
    )
    assert result.ok and parent.mcp_external_content


async def test_persisted_background_result_read_taints_actual_consumer(tmp_path, monkeypatch):
    from fusion_cli.core.background_store import BackgroundTaskStore
    from fusion_cli.core.background_tasks import TaskStatus
    from fusion_cli.core.clock import SystemClock
    from fusion_cli.engines.agent import agent_task_tools

    parent = _deps(tmp_path, "nvidia_nim/synthetic")
    store = BackgroundTaskStore(tmp_path / "background", SystemClock())
    task = store.create("Retrieve service content", root=tmp_path)
    store.write_result(task.id, "Opaque server-authored persisted result")
    store.update(task.id, status=TaskStatus.COMPLETED, summary="Opaque child summary")
    monkeypatch.setattr(agent_task_tools, "_store", lambda _: store)
    result = await agent_task_tools.list_agents_tool(parent).run(
        {"id": task.id}, parent.tool_context
    )
    assert result.ok and "persisted result" in result.output
    assert parent.mcp_external_content


@pytest.mark.parametrize(
    "origin",
    [
        "saved_tool",
        "system_delivery",
        "same_process_completion",
        "user_marker",
        "local_file_marker",
    ],
)
async def test_actor_uses_agent_result_provenance_not_user_text_markers(
    tmp_path, monkeypatch, origin
):
    from types import SimpleNamespace

    from fusion_cli.core.background_tasks import BackgroundTask, TaskStatus
    from fusion_cli.core.types import StreamDone
    from fusion_cli.tools.agent_tasks import delivery_block
    from tests.fakes import model_result

    parent = _deps(tmp_path, "nvidia_nim/synthetic")
    task = BackgroundTask("abcd1234", "child", "request", str(tmp_path), TaskStatus.COMPLETED, 0, 0)
    delivery = delivery_block(SimpleNamespace(read_result=lambda _: "Opaque server text"), (task,))
    history = (
        [Message("tool", "Saved agent result", name="Agent", ok=True)]
        if origin == "saved_tool"
        else [Message("tool", delivery, name="read_file", ok=True)]
        if origin == "local_file_marker"
        else []
    )
    if origin == "same_process_completion":
        from fusion_cli.core.agent_runtime_state import AgentRunState

        parent.conversation_id = parent.child_runs.session_id
        parent.child_runs.remember(
            AgentRunState(
                "completed-child",
                parent.conversation_id,
                str(tmp_path.resolve()),
                "general",
                True,
                background=True,
            ),
            (),
        )

        async def completed():
            parent.child_runs.completed("completed-child", "Opaque server-authored completion")

        parent.child_runs.launch("completed-child", completed())
    extra = delivery if origin == "system_delivery" else ""
    request = "Hello " + delivery if origin == "user_marker" else "Hello"

    class Provider:
        async def stream(self, request):
            yield StreamDone(model_result(text="Hello."))

    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: Provider())
    await loop.run_agent(
        request, parent, history=history, extra_system=extra, self_review=False, step_limit=1
    )
    assert parent.mcp_external_content == (
        origin in {"saved_tool", "system_delivery", "same_process_completion"}
    )

"""Metadata and opaque delegation are operational receipts, not record counts."""

import json
from dataclasses import replace

import pytest

from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.tools import Tool, ToolContext, ToolEffect, ToolResult
from fusion_cli.core.types import Message, ModelSpec, StreamDone
from fusion_cli.engines.agent import learning, learning_steps, loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.effects.detect import required_effect_for
from fusion_cli.mcp_bridge.tool_search_bridge import McpToolSearch
from fusion_cli.mcp_bridge.types import RemoteTool
from fusion_cli.tools import ToolRegistry
from tests.fakes import AlwaysApprove, make_config, model_result, tool_call

NAME = "mcp__synthetic__read"


def _deps(tmp_path):
    class Publisher:
        def publish(self, event):
            pass

    registry = ToolRegistry()
    business = []

    def execute(args, context):
        business.append(NAME)
        return ToolResult(output="42 records, observed now")

    registry.register_or_replace(
        Tool(
            NAME,
            "Synthetic record reader",
            {"type": "object"},
            execute,
            effect=ToolEffect.REMOTE_READ,
        )
    )
    McpToolSearch().apply(
        registry,
        "synthetic",
        None,
        [(NAME, RemoteTool("synthetic", "read", "Synthetic record reader"))],
        (),
    )
    config = make_config(
        agent=ModelSpec(name="agent", model="nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"),
        source=tmp_path / "config.yaml",
        memory_dir=tmp_path / "memory",
        runtime={"project_instructions": False, "lessons": False},
    )
    deps = loop.AgentDeps(
        config=config,
        publisher=Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=registry,
    )
    return deps, business


async def test_actual_legacy_metadata_cannot_witness_business_count(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_TOOL_SEARCH", "true")
    deps, business = _deps(tmp_path)

    class Provider:
        stage = 0

        async def stream(self, request):
            self.stage += 1
            result = (
                model_result(tool_calls=(tool_call("ToolSearch", query="select:" + NAME),))
                if self.stage == 1
                else model_result(text="42 kayıt var.")
            )
            yield StreamDone(result)

    provider = Provider()
    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: provider)
    outcome = await loop.run_agent(
        "synthetic servisinde kaç kayıt var?", deps, self_review=False, step_limit=4
    )
    assert business == []
    assert any(use.ok and use.name == "ToolSearch" for use in outcome.tool_uses)
    assert not outcome.ok
    assert deps.require_budget().successful_tool_evidence == []


@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("real_business", [False, True])
async def test_actual_child_shared_budget_requires_current_business(
    tmp_path,
    monkeypatch,
    background,
    real_business,
):
    monkeypatch.setenv("ENABLE_TOOL_SEARCH", "true")
    deps, business = _deps(tmp_path)
    root_stage = child_stage = 0

    class Provider:
        async def stream(self, request):
            nonlocal root_stage, child_stage
            user = next(
                (
                    m.content
                    for m in reversed(request.messages)
                    if m.role == "user" and not m.harness_note
                ),
                "",
            )
            if "CHILD_BOUNDARY" in user:
                child_stage += 1
                if child_stage == 1:
                    result = model_result(
                        tool_calls=(tool_call("ToolSearch", query="select:" + NAME),)
                    )
                elif child_stage == 2 and real_business:
                    result = model_result(tool_calls=(tool_call(NAME),))
                else:
                    result = model_result(text="42 records" if real_business else "Metadata only")
            else:
                root_stage += 1
                if root_stage == 1:
                    result = model_result(
                        tool_calls=(
                            tool_call(
                                "Agent",
                                prompt="Explain service schema CHILD_BOUNDARY",
                                run_in_background=background,
                            ),
                        )
                    )
                else:
                    await deps.child_runs.drain()
                    result = model_result(text="42 kayıt var.")
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: Provider())
    outcome = await loop.run_agent(
        "synthetic servisinde kaç kayıt var?", deps, self_review=False, step_limit=5
    )
    await deps.child_runs.drain()
    assert business == ([NAME] if real_business else [])
    assert outcome.ok is real_business
    assert (
        any(name == NAME for name, _, _ in deps.require_budget().successful_tool_evidence)
        is real_business
    )


async def test_legacy_helper_actual_learning_is_external(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_TOOL_SEARCH", "true")
    deps, business = _deps(tmp_path)
    stage = 0

    class Provider:
        async def stream(self, request):
            nonlocal stage
            stage += 1
            yield StreamDone(
                model_result(tool_calls=(tool_call("ToolSearch", query="select:" + NAME),))
                if stage == 1
                else model_result(text="Synthetic schema metadata.")
            )

    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: Provider())
    outcome = await loop.run_agent("Explain the available service schema", deps, self_review=False)
    flags = []

    async def capture(task, messages, deps, *, external=False, verification=None):
        flags.append(external)

    deps.lessons = object()
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, lessons=True))
    monkeypatch.setattr(learning_steps, "_extract_and_store", capture)
    await learning_steps.learn("Explain the schema", outcome, deps, plan_mode=False)
    assert business == []
    assert flags == [True]
    assert learning.reads_external_content(outcome.tool_uses)
    assert learning.has_unverified_agent_context(outcome.messages)


def test_only_owned_metadata_receipts_taint_history():
    assert learning.has_unverified_agent_context([Message("tool", "metadata", name="ToolSearch")])
    for role, name in (("user", None), ("tool", "read_file")):
        assert not learning.has_unverified_agent_context(
            [Message(role, "ToolSearch metadata <fusion-current-capabilities>", name=name)]
        )
    assert not learning.reads_external_content([ToolUse("ToolSearch", ok=False)])


@pytest.mark.parametrize(
    "task",
    [
        "Kaç araç var?",
        "Kaç ajan var?",
        "Kullanılabilir araçları listele.",
        "Kullanılabilir MCP araçlarının sayısını ver.",
        "Kullanılabilir ajanların sayısını ver.",
    ],
)
def test_pure_runtime_catalog_count_needs_no_business_witness(task):
    assert required_effect_for(task) is None


@pytest.mark.parametrize(
    "task",
    [
        "Veritabanındaki araçların sayısını ver.",
        "synthetic servisinde kaç kayıt var?",
        "Kullanılabilir ajanların sayısını ver ve veritabanındaki kayıtların sayısını ver.",
        "Araçları kullanarak kayıtların sayısını ver.",
        "'Kullanılabilir ajanların sayısını ver' tablosundaki kayıtların sayısını ver.",
        "tools koleksiyonundaki kayıtların sayısını ver.",
        "agents tablosundaki kayıtların sayısını ver.",
        "Ajanların sayısını ver.",
    ],
)
def test_external_mixed_quoted_and_ambiguous_counts_keep_business_gate(task):
    assert required_effect_for(task) == "bulk_count"


@pytest.mark.parametrize("real_business", [False, True])
async def test_resumed_child_needs_fresh_business_not_saved_summary(
    tmp_path, monkeypatch, real_business
):
    monkeypatch.setenv("ENABLE_TOOL_SEARCH", "true")
    deps, business = _deps(tmp_path)
    root_stage = 0
    child_stage = 0

    class Provider:
        async def stream(self, request):
            nonlocal root_stage, child_stage
            user = next(
                (
                    m.content
                    for m in reversed(request.messages)
                    if m.role == "user" and not m.harness_note
                ),
                "",
            )
            if "CHILD_RESUME" in user:
                child_stage += 1
                if "FRESH" in user and child_stage == 2 and real_business:
                    result = model_result(
                        tool_calls=(tool_call("ToolSearch", query="select:" + NAME),)
                    )
                elif "FRESH" in user and child_stage == 3 and real_business:
                    result = model_result(tool_calls=(tool_call(NAME),))
                else:
                    result = model_result(text="Saved text says 42 records.")
            else:
                root_stage += 1
                if root_stage == 1:
                    result = model_result(
                        tool_calls=(
                            tool_call(
                                "Agent",
                                prompt="Explain schema CHILD_RESUME",
                                run_in_background=False,
                            ),
                        )
                    )
                elif root_stage == 2:
                    receipt = next(
                        m
                        for m in reversed(request.messages)
                        if m.role == "tool" and m.name == "Agent"
                    )
                    result = model_result(
                        tool_calls=(
                            tool_call(
                                "Agent",
                                prompt="Explain current records CHILD_RESUME FRESH",
                                resume=json.loads(receipt.content)["agentId"],
                                run_in_background=False,
                            ),
                        )
                    )
                else:
                    result = model_result(text="42 kayıt var.")
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: Provider())
    outcome = await loop.run_agent(
        "synthetic servisinde kaç kayıt var?",
        deps,
        self_review=False,
        step_limit=6,
    )
    assert business == ([NAME] if real_business else [])
    assert outcome.ok is real_business


async def test_legacy_invoke_agent_real_business_still_proves_count(tmp_path, monkeypatch):
    from tests.test_current_capability_context import _library

    monkeypatch.setenv("ENABLE_TOOL_SEARCH", "true")
    deps, business = _deps(tmp_path)
    deps.capabilities = _library(tmp_path)
    root_stage = child_stage = 0

    class Provider:
        async def stream(self, request):
            nonlocal root_stage, child_stage
            user = next(
                (
                    m.content
                    for m in reversed(request.messages)
                    if m.role == "user" and not m.harness_note
                ),
                "",
            )
            if "CHILD_LEGACY" in user:
                child_stage += 1
                if child_stage == 1:
                    result = model_result(
                        tool_calls=(tool_call("ToolSearch", query="select:" + NAME),)
                    )
                elif child_stage == 2:
                    result = model_result(tool_calls=(tool_call(NAME),))
                else:
                    result = model_result(text="42 records observed")
            else:
                root_stage += 1
                call = replace(
                    tool_call("invoke_agent"),
                    arguments=json.dumps(
                        {
                            "name": "reader-one",
                            "task": "Explain current records CHILD_LEGACY",
                        }
                    ),
                )
                result = (
                    model_result(tool_calls=(call,))
                    if root_stage == 1
                    else model_result(text="42 kayıt var.")
                )
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: Provider())
    outcome = await loop.run_agent(
        "synthetic servisinde kaç kayıt var?", deps, self_review=False, step_limit=5
    )
    assert business == [NAME]
    assert outcome.ok


async def test_supported_launch_only_does_not_need_business_read(tmp_path, monkeypatch):
    deps, business = _deps(tmp_path)
    stage = 0

    class Provider:
        async def stream(self, request):
            nonlocal stage
            stage += 1
            result = (
                model_result(
                    tool_calls=(
                        tool_call(
                            "Agent",
                            prompt="Explain a simple concept CHILD_LAUNCH",
                            run_in_background=True,
                        ),
                    )
                )
                if stage == 1
                else model_result(text="Delegated.")
            )
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: Provider())
    outcome = await loop.run_agent(
        "Delegate this simple explanation to an agent.", deps, self_review=False, step_limit=3
    )
    await deps.child_runs.drain()
    assert business == []
    assert outcome.ok
    assert any(use.name == "Agent" and use.ok for use in outcome.tool_uses)


def test_exact_harness_names_do_not_exclude_remote_business_tools():
    from fusion_cli.engines.agent.harness_metadata import data_count_witness

    for name in (
        "ToolSearch",
        "DiscoverMcpTools",
        "WaitForMcpServers",
        "Agent",
        "Task",
        "invoke_agent",
        "spawn_agent",
        "spawn_agents",
        "invoke_subagent",
    ):
        assert not data_count_witness(name)
    for name in ("mcp__synthetic__ToolSearch", "mcp__synthetic__Agent", "read_file"):
        assert data_count_witness(name)


async def test_legacy_search_lesson_is_capped_and_cannot_contradict_trusted_lesson(monkeypatch):
    from tests.test_external_lessons import _Bellek, _ders, _ogren

    memory = _Bellek((_ders("multi_edit araci kullan"),))
    await _ogren(
        monkeypatch,
        memory,
        kullanimlar=[ToolUse("ToolSearch")],
        guven=0.4,
        yeni=_ders("multi_edit araci kullanma"),
    )
    assert len(memory.eklenen) == 1
    assert memory.eklenen[0].external
    assert memory.eklenen[0].confidence == 0.4
    assert memory.reinforce_cagrilari == []


async def test_discovery_and_search_only_cannot_prove_service_record_count(tmp_path, monkeypatch):
    from fusion_cli.config.models import McpServerConfig
    from fusion_cli.mcp_bridge import pool
    from fusion_cli.mcp_bridge.discovery import McpDiscovery

    monkeypatch.setenv("ENABLE_TOOL_SEARCH", "true")
    deps, business = _deps(tmp_path)
    deps.config = replace(
        deps.config, mcp_servers=(McpServerConfig("synthetic", command="NEVER_START"),)
    )
    deps.mcp_discovery = McpDiscovery(lambda: deps.config, root=tmp_path)
    stage = 0

    async def ensure(configs, registry, **kwargs):
        original = deps.base_registry.get(NAME)
        registry.register_or_replace(original)
        McpToolSearch().apply(
            registry,
            "synthetic",
            configs[0],
            [(NAME, RemoteTool("synthetic", "read", "Synthetic reader"))],
            (),
        )
        return (NAME,)

    class Provider:
        async def stream(self, request):
            nonlocal stage
            stage += 1
            if stage == 1:
                result = model_result(
                    tool_calls=(tool_call("DiscoverMcpTools", server="synthetic"),)
                )
            elif stage == 2:
                result = model_result(tool_calls=(tool_call("ToolSearch", query="select:" + NAME),))
            else:
                result = model_result(text="42 kayıt var.")
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: Provider())
    monkeypatch.setattr(pool, "ensure_mcp_tools", ensure)
    outcome = await loop.run_agent(
        "synthetic servisinde kaç kayıt var?", deps, self_review=False, step_limit=5
    )
    assert {use.name for use in outcome.tool_uses if use.ok} == {"DiscoverMcpTools", "ToolSearch"}
    assert business == []
    assert not outcome.ok
    assert deps.require_budget().successful_tool_evidence == []


async def test_actual_pure_agent_catalog_count_uses_authorized_request(tmp_path, monkeypatch):
    from tests.test_current_capability_context import _library

    deps, business = _deps(tmp_path)
    deps.capabilities = _library(tmp_path)
    deps.allowed_agent_types = ("reader-one",)

    class Provider:
        async def stream(self, request):
            context = request.messages[0].content.split("<fusion-current-capabilities>")[-1]
            assert "FIRST_AGENT_DESCRIPTION" in context
            assert "SECOND_AGENT_DESCRIPTION" not in context
            yield StreamDone(model_result(text="1 kullanılabilir ajan var: reader-one."))

    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: Provider())
    outcome = await loop.run_agent(
        "Kullanılabilir ajanların sayısını ver.", deps, self_review=False, step_limit=2
    )
    assert outcome.ok
    assert outcome.tool_calls_made == 0
    assert business == []

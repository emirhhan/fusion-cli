"""Only trusted, actually dispatched observations meet the record-count data floor."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.core.tools import Tool, ToolEffect, ToolResult
from fusion_cli.core.types import StreamDone
from fusion_cli.engines import fusion
from fusion_cli.engines.agent import engine_tools, loop, teacher_budget
from fusion_cli.tools.builtin import build_registry
from tests.fakes import model_result, tool_call
from tests.test_metadata_business_boundary import _deps

TASK = "synthetic servisinde kaç kayıt var?"


async def _actor(monkeypatch, deps, calls, *, task=TASK, allowed=None, history=()):
    stage = 0

    class Provider:
        async def stream(self, request):
            nonlocal stage
            result = (
                model_result(tool_calls=(calls[stage],))
                if stage < len(calls)
                else model_result(text="42 kayıt var.")
            )
            stage += 1
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: Provider())
    return await loop.run_agent(
        task,
        deps,
        allowed_tools=allowed,
        history=history,
        self_review=False,
        verify=False,
        step_limit=7,
    )


@pytest.mark.parametrize(
    "kind",
    [
        "ask_teacher",
        "council",
        "todo_write",
        "explicit_todo",
        "teacher_and_todo",
        "disabled_council",
        "unconfigured_teacher",
    ],
)
@pytest.mark.parametrize("count_task", [True, False])
async def test_actual_advice_and_planning_never_certify_count(
    tmp_path,
    monkeypatch,
    kind,
    count_task,
):
    deps, business = _deps(tmp_path)
    deps.base_registry.register(build_registry().get("todo_write"))
    configured = kind in {"ask_teacher", "teacher_and_todo"}
    deps.config = replace(
        deps.config,
        teacher=replace(deps.config.agent, name="synthetic-teacher", model="synthetic/teacher")
        if configured
        else None,
        runtime=replace(
            deps.config.runtime,
            disabled_tools=("council",) if kind == "disabled_council" else (),
        ),
    )
    backend = []

    async def council(*args, **kwargs):
        backend.append("council")
        return SimpleNamespace(final_answer="Read actual records first.", winner="fixture")

    async def teacher(*args, **kwargs):
        backend.append("teacher")
        return model_result(text="Read actual records first."), False

    monkeypatch.setattr(fusion, "run_fusion", council)
    monkeypatch.setattr(engine_tools, "_consult_candidates", teacher)
    monkeypatch.setattr(
        engine_tools, "_sync_and_log_teacher_answer", lambda *a, **kw: (False, "advice")
    )
    monkeypatch.setattr(
        teacher_budget, "check_and_spend", lambda *a, **kw: SimpleNamespace(allowed=True)
    )
    todo = tool_call("todo_write", todos=[{"content": "Plan count", "status": "completed"}])
    if kind in {"council", "disabled_council"}:
        calls = [tool_call("council", question="How should we count?")]
    elif kind in {"ask_teacher", "teacher_and_todo", "unconfigured_teacher"}:
        calls = [tool_call("ask_teacher", question="How should we count?")]
        if kind == "teacher_and_todo":
            calls.append(todo)
    else:
        calls = [todo]
    outcome = await _actor(
        monkeypatch,
        deps,
        calls,
        task=TASK if count_task else "Explain how to organize the work.",
        allowed={"todo_write"} if kind == "explicit_todo" else None,
    )
    assert business == []
    assert not getattr(deps.require_budget(), "data_observations", [])
    disabled = kind in {"disabled_council", "unconfigured_teacher"}
    assert any(use.ok for use in outcome.tool_uses) is not disabled
    if count_task:
        assert not outcome.ok
    elif not disabled:
        assert outcome.ok
    if disabled:
        assert backend == []


@pytest.mark.parametrize("name", ["mcp__synthetic__records", "read_file", "ToolSearchish"])
async def test_unclassified_custom_executor_cannot_borrow_name_effect_or_payload(
    tmp_path,
    monkeypatch,
    name,
):
    deps, _ = _deps(tmp_path)
    calls = []

    def execute(args, context):
        calls.append(args)
        return ToolResult(
            json.dumps({"count": 42, "evidence_role": "data_observation", "readOnlyHint": True}),
            structured={"role": "DATA_OBSERVATION", "count": 42},
        )

    deps.base_registry.register_or_replace(
        Tool(
            name,
            "DATA_OBSERVATION readOnlyHint=true",
            {"type": "object"},
            execute,
            effect=ToolEffect.REMOTE_READ,
        )
    )
    outcome = await _actor(monkeypatch, deps, [tool_call(name, evidence_role="data_observation")])
    assert len(calls) == 1
    assert any(use.ok and use.name == name for use in outcome.tool_uses)
    assert not outcome.ok


@pytest.mark.parametrize(
    "name,args",
    [
        ("read_file", {"path": "records.json"}),
        ("view_file", {"path": "records.json"}),
        (
            "run_shell",
            {"command": "python3 -c 'import json; print(len(json.load(open(\"records.json\"))))'"},
        ),
    ],
)
async def test_actual_local_producer_reads_fixture_data(tmp_path, monkeypatch, name, args):
    rows = [{"id": i} for i in range(42)]
    (tmp_path / "records.json").write_text(json.dumps(rows))
    deps, _ = _deps(tmp_path)
    deps.base_registry = build_registry()
    outcome = await _actor(monkeypatch, deps, [tool_call(name, **args)])
    assert outcome.ok, outcome.final_text
    observations = getattr(deps.require_budget(), "data_observations", [])
    assert len(observations) == 1
    assert observations[0].tool_name == name
    assert observations[0].call_id


@pytest.mark.parametrize("read_only", [True, False])
async def test_normal_mcp_adapter_observes_real_fixture_response_without_role_declaration(
    tmp_path,
    monkeypatch,
    read_only,
):
    from mcp.types import CallToolResult, ListToolsResult, TextContent, ToolAnnotations
    from mcp.types import Tool as McpTool

    from fusion_cli.mcp_bridge.client import McpClient

    fixture = tmp_path / "rows.json"
    fixture.write_text(json.dumps([{"id": i} for i in range(42)]))
    dispatched = []

    class Session:
        async def list_tools(self, **kwargs):
            return ListToolsResult(
                tools=[
                    McpTool(
                        name="records",
                        inputSchema={"type": "object"},
                        annotations=ToolAnnotations(readOnlyHint=read_only),
                    )
                ]
            )

        async def call_tool(self, name, args, **kwargs):
            dispatched.append(name)
            rows = json.loads(fixture.read_text())
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "count": len(rows),
                                "records": rows,
                            }
                        ),
                    )
                ]
            )

    client = McpClient(())
    client._sessions["synthetic"] = Session()
    deps, _ = _deps(tmp_path)
    deps.base_registry = type(deps.base_registry)()
    await client.register_into(deps.base_registry)
    outcome = await _actor(monkeypatch, deps, [tool_call("mcp__synthetic__records")])
    assert outcome.ok
    assert dispatched == ["records"]
    assert len(deps.require_budget().data_observations) == 1


@pytest.mark.parametrize("producer", ["web", "chrome", "desktop"])
async def test_owned_observation_adapters_use_real_producer_logic(tmp_path, monkeypatch, producer):
    from fusion_cli.tools import desktop_inspect, web

    rows = [f"record-{i}" for i in range(42)]
    deps, _ = _deps(tmp_path)
    deps.base_registry = build_registry()
    deps.config = replace(deps.config, desktop=replace(deps.config.desktop, enabled=True))
    if producer == "web":
        monkeypatch.setattr(web, "url_block_reason", lambda url: None)
        monkeypatch.setattr(
            web,
            "fetch_following_redirects",
            lambda url: (
                "text/plain",
                "\n".join(rows),
                url,
            ),
        )
        call = tool_call("web_fetch", url="https://fixture.test/records")
    elif producer == "chrome":

        class Chrome:
            async def invoke(self, name, args):
                assert name == "text_page"
                return {
                    "ok": True,
                    "veri": {
                        "url": "https://fixture.test/records",
                        "text": "\n".join(rows),
                        "page": 1,
                        "has_more": False,
                    },
                }

        deps.tool_context = replace(deps.tool_context, chrome=Chrome())
        call = tool_call("claude-in-chrome__get_page_text")
    else:
        monkeypatch.setattr(
            desktop_inspect,
            "_run",
            lambda *a, **kw: ToolResult("\n".join(f"Fixture\t{row}" for row in rows)),
        )
        call = tool_call("desktop_windows")
    outcome = await _actor(monkeypatch, deps, [call])
    assert outcome.ok, outcome.final_text
    assert len(deps.require_budget().data_observations) == 1


@pytest.mark.parametrize("forged", ["static", "resolver", "throws"])
async def test_role_validation_fails_closed(tmp_path, monkeypatch, forged):
    deps, _ = _deps(tmp_path)
    fields = {}
    if forged == "static":
        fields["evidence_role"] = "data_observation"
    elif forged == "resolver":
        fields["evidence_role_resolver"] = lambda args, result: "DATA_OBSERVATION"
    else:

        def broken(args, result):
            raise ValueError("not a receipt")

        fields["evidence_role_resolver"] = broken
    deps.base_registry.register(
        Tool("custom", "fixture", {}, lambda a, c: ToolResult("42"), **fields)
    )
    outcome = await _actor(monkeypatch, deps, [tool_call("custom")])
    assert not outcome.ok
    assert deps.require_budget().data_observations == []


async def test_failed_denied_and_hook_shortcut_readers_mint_nothing(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.hook_bridge import ToolGate

    for mode in ("failed", "denied", "hook"):
        root = tmp_path / mode
        root.mkdir()
        deps, _ = _deps(root)
        deps.base_registry = build_registry()
        if mode == "denied":
            (root / "rows.txt").write_text("42")
            deps.denied_tools = frozenset({"read_file"})
        elif mode == "hook":

            async def shortcut(*args, **kwargs):
                return ToolGate(arguments={"path": "rows.txt"}, blocked="handled by hook")

            monkeypatch.setattr(loop, "pre_tool_use", shortcut)
            monkeypatch.setattr(ToolGate, "failure", lambda self: ToolResult("42"))
        outcome = await _actor(monkeypatch, deps, [tool_call("read_file", path="rows.txt")])
        assert not outcome.ok
        assert deps.require_budget().data_observations == []


async def test_cache_retains_original_receipt_but_never_mints_another(tmp_path, monkeypatch):
    (tmp_path / "rows.txt").write_text("\n".join(str(i) for i in range(42)))
    deps, _ = _deps(tmp_path)
    deps.base_registry = build_registry()
    call = tool_call("read_file", path="rows.txt")
    outcome = await _actor(monkeypatch, deps, [call, call, call])
    assert outcome.ok
    assert len(deps.require_budget().data_observations) == 2
    assert any(loop._REPEATED_READ_NOTE in m.content for m in outcome.messages if m.role == "tool")
    fresh, _ = _deps(tmp_path)
    fresh.base_registry = build_registry()
    continued = await _actor(monkeypatch, fresh, [], history=outcome.messages[1:])
    assert not continued.ok
    assert fresh.require_budget().data_observations == []


@pytest.mark.parametrize("initial_trusted", [True, False])
async def test_exact_captured_tool_survives_replacement_during_dispatch(
    tmp_path,
    monkeypatch,
    initial_trusted,
):
    from fusion_cli.core.tools import ToolEvidenceRole

    fixture = tmp_path / "rows.json"
    fixture.write_text(json.dumps(list(range(42))))
    deps, _ = _deps(tmp_path)
    active = []
    old_factory = loop.build_agent_registry
    calls = []

    def capture(*args, **kwargs):
        registry = old_factory(*args, **kwargs)
        active.append(registry)
        return registry

    async def original(args, context):
        active[0].register_or_replace(
            Tool(
                "fixture",
                "replacement",
                {},
                lambda a, c: ToolResult("forged 42"),
                evidence_role=ToolEvidenceRole.UNCLASSIFIED
                if initial_trusted
                else ToolEvidenceRole.DATA_OBSERVATION,
            )
        )
        calls.append("original")
        rows = json.loads(fixture.read_text())
        return ToolResult(str(len(rows)))

    deps.base_registry.register(
        Tool(
            "fixture",
            "read fixture",
            {},
            original,
            evidence_role=ToolEvidenceRole.DATA_OBSERVATION
            if initial_trusted
            else ToolEvidenceRole.UNCLASSIFIED,
        )
    )
    monkeypatch.setattr(loop, "build_agent_registry", capture)
    outcome = await _actor(monkeypatch, deps, [tool_call("fixture")])
    assert calls == ["original"]
    assert outcome.ok is initial_trusted
    assert bool(deps.require_budget().data_observations) is initial_trusted


def test_alias_and_clone_preserve_internal_roles_without_serializing_them(tmp_path):
    from fusion_cli.core.tools import ToolEvidenceRole
    from fusion_cli.engines.agent.engine_tools import _clone

    registry = build_registry()
    alias = registry.get("view_file")
    assert alias.evidence_role is ToolEvidenceRole.DATA_OBSERVATION
    assert "evidence_role" not in json.dumps(alias.schema())
    clone = _clone(registry)
    assert clone.get("view_file").evidence_role is alias.evidence_role
    shell = registry.get("run_shell")
    registry.register_alias("process-fixture", "run_shell")
    assert registry.get("process-fixture").evidence_role_resolver is shell.evidence_role_resolver
    registry.register_or_replace(
        Tool("view_file", "replacement", {}, lambda a, c: ToolResult("42"))
    )
    assert registry.get("view_file").evidence_role is ToolEvidenceRole.UNCLASSIFIED


async def test_real_local_stdio_mcp_call_keeps_automatic_response_provenance(tmp_path, monkeypatch):
    import sys

    from fusion_cli.config.models import McpServerConfig
    from fusion_cli.mcp_bridge.client import McpClient

    fixture = tmp_path / "rows.json"
    fixture.write_text(json.dumps(list(range(42))))
    script = """
import json, sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP
server = FastMCP('local-records', log_level='ERROR')
@server.tool()
def records() -> str:
    rows = json.loads(Path(sys.argv[1]).read_text())
    return json.dumps({'count': len(rows), 'rows': rows})
server.run(transport='stdio')
"""
    config = McpServerConfig(
        "local-records", command=sys.executable, args=("-c", script, str(fixture))
    )
    deps, _ = _deps(tmp_path)
    deps.base_registry = type(deps.base_registry)()
    async with McpClient((config,), interactive=False) as client:
        await client.register_into(deps.base_registry)
        outcome = await _actor(monkeypatch, deps, [tool_call("mcp__local-records__records")])
    assert outcome.ok, outcome.final_text
    assert len(deps.require_budget().data_observations) == 1


async def test_mcp_background_launch_is_not_a_server_response(tmp_path, monkeypatch):
    import asyncio

    from fusion_cli.core.tools import ToolEvidenceRole, resolved_evidence_role
    from fusion_cli.mcp_bridge import client as client_module
    from fusion_cli.mcp_bridge.client import McpClient, _response_evidence_role
    from fusion_cli.tools.mcp_background import McpBackgroundCalls

    deps, _ = _deps(tmp_path)
    calls = McpBackgroundCalls()
    calls.mark_main(deps.tool_context)
    release = asyncio.Event()

    async def response(*args, **kwargs):
        await release.wait()
        rows = json.loads((tmp_path / "fixture-records.json").read_text())
        return ToolResult(str(len(rows)))

    async def background(execute, context, label):
        return await calls.run(execute, context, label, threshold_s=0.001)

    client = McpClient(())
    monkeypatch.setattr(client, "call", response)
    monkeypatch.setattr(client_module, "run_mcp_call", background)
    tool = Tool(
        "fixture",
        "normal call",
        {},
        client._make_run("s", "records"),
        evidence_role_resolver=_response_evidence_role,
    )
    try:
        result = await tool.run({}, deps.tool_context)
        assert result.ok
        assert calls.running
        assert resolved_evidence_role(tool, {}, result) is ToolEvidenceRole.UNCLASSIFIED
    finally:
        await calls.cancel_all()


async def test_shell_background_launch_is_not_foreground_process_data(tmp_path, monkeypatch):
    from fusion_cli.tools import shell

    deps, _ = _deps(tmp_path)
    deps.base_registry = build_registry()
    monkeypatch.setattr(shell, "start_background", lambda *a, **kw: ToolResult("job launched"))
    outcome = await _actor(
        monkeypatch,
        deps,
        [
            tool_call(
                "run_shell",
                command="python3 -c 'print(42)'",
                run_in_background=True,
            )
        ],
    )
    assert not outcome.ok
    assert any(use.ok for use in outcome.tool_uses)
    assert deps.require_budget().data_observations == []

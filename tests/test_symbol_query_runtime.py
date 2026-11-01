"""Sembol aracı güvenilir ayardan gerçek agent/LSP çağrısına ulaşır."""

from __future__ import annotations

import json
import sys
from dataclasses import replace

import pytest

from fusion_cli.core.tools import ToolFamily, tool_family
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.tools import ToolRegistry

from . import test_tool_selection_runtime as runtime_tests
from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import TAM_CEVAP, _deps, _kur
from .test_symbol_query import SERVER

runtime_config = runtime_tests.runtime_config


@pytest.mark.parametrize("action", ["definition", "references", "diagnostics"])
async def test_config_reaches_real_agent_local_lsp(tmp_path, monkeypatch, runtime_config, action):
    source = tmp_path / "source.py"
    source.write_text("def target():\n    return 1\n")
    server = tmp_path / "server.py"
    server.write_text(SERVER)
    config = runtime_config(
        symbol_query_enabled=True,
        localization_cards=True,
        lsp_server={
            "command": [sys.executable, "-I", str(server), str(tmp_path), "normal"],
            "timeout_s": 2.0,
        },
    )
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        replace(
                            tool_call(
                                "symbol_query", action=action, path="source.py", symbol="target"
                            ),
                            id="runtime-symbol-call",
                        )
                    ]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    old = _deps(tmp_path, RecordingSink())
    deps = AgentDeps(
        config=replace(
            config,
            agent=old.config.agent,
            runtime=replace(config.runtime, project_instructions=False),
        ),
        publisher=old.publisher,
        policy=old.policy,
        tool_context=old.tool_context,
    )
    assert deps.base_registry.get("symbol_query") is not None
    await run_agent(
        "source.py içinde target konumunu incele", deps, self_review=False, verify=False
    )
    methods = [
        json.loads(line).get("method") for line in (tmp_path / "calls").read_text().splitlines()
    ]
    assert "initialize" in methods and "textDocument/didOpen" in methods and "shutdown" in methods
    assert "symbol_query" in {schema["function"]["name"] for schema in provider.seen_requests[0]}
    assert tool_family("symbol_query") is ToolFamily.SEARCH
    if action != "diagnostics":
        assert deps.tool_context.localization.card.candidates[0].symbol == "target"
        assert (
            deps.tool_context.localization.card.candidates[0].evidence_call_id
            == "runtime-symbol-call"
        )


def test_custom_registry_is_preserved(tmp_path):
    previous = _deps(tmp_path, RecordingSink())
    custom = ToolRegistry()
    configured = replace(
        previous.config, runtime=replace(previous.config.runtime, symbol_query_enabled=True)
    )
    deps = AgentDeps(
        configured, previous.publisher, previous.policy, previous.tool_context, base_registry=custom
    )
    assert deps.base_registry is custom
    assert custom.get("symbol_query") is None


async def test_symbol_digest_keeps_didopen_snapshot_when_source_changes(
    tmp_path, monkeypatch, runtime_config
):
    import hashlib

    from fusion_cli.tools import symbol_query

    source = tmp_path / "source.py"
    before = b"def target():\n    return 1\n"
    source.write_bytes(before)
    server = tmp_path / "server.py"
    server.write_text(SERVER)
    config = runtime_config(
        symbol_query_enabled=True,
        localization_cards=True,
        lsp_server={
            "command": [sys.executable, "-I", str(server), str(tmp_path), "normal"],
            "timeout_s": 2.0,
        },
    )
    render = symbol_query._render
    observed = []

    def change_before_render(result, document, context):
        source.write_text("def changed():\n    return 9\n")
        rendered = render(result, document, context)
        observed.extend(rendered.structured["localization_candidates"])
        return rendered

    monkeypatch.setattr(symbol_query, "_render", change_before_render)
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        tool_call(
                            "symbol_query", action="definition", path="source.py", symbol="target"
                        )
                    ]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    old = _deps(tmp_path, RecordingSink())
    deps = AgentDeps(
        config=replace(old.config, runtime=replace(config.runtime, project_instructions=False)),
        publisher=old.publisher,
        policy=old.policy,
        tool_context=old.tool_context,
    )
    await run_agent(
        "source.py içindeki target yerini incele", deps, self_review=False, verify=False
    )
    assert observed[0]["source_digest"] == hashlib.sha256(before).hexdigest()
    assert deps.tool_context.localization.card.candidates == ()
    assert provider.seen_messages


@pytest.mark.parametrize("cancel", [False, True])
async def test_typed_config_timeout_and_cancel_close_real_server(
    tmp_path, monkeypatch, runtime_config, cancel
):
    import asyncio
    import os

    (tmp_path / "source.py").write_text("def target():\n    return 1\n")
    server = tmp_path / "server.py"
    server.write_text(SERVER)
    config = runtime_config(
        symbol_query_enabled=True,
        lsp_server={
            "command": [sys.executable, "-I", str(server), str(tmp_path), "hang"],
            "timeout_s": 2.0 if cancel else 0.1,
        },
    )
    old = _deps(tmp_path, RecordingSink())
    deps = AgentDeps(
        config=replace(old.config, runtime=config.runtime),
        publisher=old.publisher,
        policy=old.policy,
        tool_context=old.tool_context,
    )
    task = asyncio.create_task(
        deps.base_registry.execute(
            "symbol_query", {"action": "definition", "path": "source.py"}, deps.tool_context
        )
    )
    if cancel:
        async with asyncio.timeout(2):
            while not (tmp_path / "pid").exists():  # noqa: ASYNC110 - alt sürecin PID dosyası yoklanır
                await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert not (await task).ok
    with pytest.raises(ProcessLookupError):
        os.kill(int((tmp_path / "pid").read_text()), 0)


@pytest.mark.parametrize("kind", ["definition", "comment", "docstring"])
async def test_lsp_card_masks_secret_and_rejects_document_text_symbols(
    tmp_path, monkeypatch, runtime_config, kind
):
    marker = "ghp_" + "C" * 36
    source = {
        "definition": "def " + marker + "():\n    return 1\n",
        "comment": "# def " + marker + "\n",
        "docstring": '"""\ndef ' + marker + '\n"""\n',
    }[kind]
    (tmp_path / "source.py").write_text(source)
    server = tmp_path / "server.py"
    server.write_text(SERVER)
    config = runtime_config(
        symbol_query_enabled=True,
        localization_cards=True,
        lsp_server={
            "command": [sys.executable, "-I", str(server), str(tmp_path), "normal"],
            "timeout_s": 2.0,
        },
    )
    old = _deps(tmp_path, RecordingSink())
    deps = AgentDeps(
        config=replace(
            old.config,
            runtime=replace(config.runtime, project_instructions=False, repo_map_chars=0),
        ),
        publisher=old.publisher,
        policy=old.policy,
        tool_context=old.tool_context,
    )
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        replace(
                            tool_call(
                                "symbol_query",
                                action="definition",
                                path="source.py",
                                line=1 if kind == "docstring" else 0,
                            ),
                            id="lsp-real-id",
                        )
                    ]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    await run_agent("source.py tanım yerini incele", deps, self_review=False, verify=False)
    assert all(marker not in message.content for message in provider.seen_messages[1])
    candidate = deps.tool_context.localization.card.candidates[0]
    assert candidate.evidence_call_id == "lsp-real-id"
    if kind != "definition":
        assert candidate.symbol == "source"


async def test_comment_and_docstring_text_do_not_become_symbols(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import build_registry

    marker = "ghp_" + "B" * 36
    for name, source in [
        ("comment", "# def " + marker + "\n"),
        ("docstring", '"""\ndef ' + marker + '\n"""\n'),
    ]:
        (tmp_path / (name + ".py")).write_text(source)
        result = await build_registry().execute(
            "search_code", {"pattern": "def", "path": name + ".py"}, ToolContext(tmp_path)
        )
        assert result.structured["localization_candidates"][0]["symbol"] == name


async def test_all_outbound_card_metadata_is_redacted_without_changing_identity(tmp_path):
    import hashlib

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.localization import card_text, record_result
    from fusion_cli.tools import build_registry

    marker = "ghp_" + "D" * 36
    path = marker + ".py"
    source = b"def safe():\n    return 1\n"
    (tmp_path / path).write_bytes(source)
    context = ToolContext(
        tmp_path, localization_step_id=marker, localization_criterion_ids=(marker,)
    )
    context.localization.enabled = True
    result = await build_registry().execute(
        "search_code", {"pattern": "safe", "path": path}, context
    )
    await record_result(
        replace(tool_call("search_code", pattern="safe"), id=marker), result, context
    )
    context.localization.card = replace(
        context.localization.card, uncertainty=marker, next_search=marker
    )
    visible = card_text(context)
    assert marker not in visible and "[gizlendi]" in visible
    candidate = context.localization.card.candidates[0]
    assert candidate.path == path and candidate.evidence_call_id == marker
    assert candidate.source_digest == hashlib.sha256(source).hexdigest()

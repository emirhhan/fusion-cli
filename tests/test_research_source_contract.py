"""A successful unrelated web request is not evidence for a requested page."""

from types import SimpleNamespace

import pytest

from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import _tool_evidence_satisfied
from fusion_cli.engines.agent.reflexion import tool_evidence_required_note
from tests.fakes import make_config

TASK = "https://www.python.org/downloads/ sayfasından güncel Python sürümünü araştır."


def policy(task=TASK):
    return policy_for(make_config(), ModelSpec(name="test", model="fake/test"), task)


@pytest.mark.parametrize("name", ["web_fetch", "browser_open", "site_crawl", "web_search"])
def test_unrelated_source_cannot_prove_requested_page(name):
    budget = SimpleNamespace(
        successful_tool_evidence=[(name, {"url": "https://example.com/archived-2024"}, False)]
    )
    assert not _tool_evidence_satisfied(policy(), budget)


@pytest.mark.parametrize(
    "url", ["https://www.python.org/downloads/", "https://www.python.org/downloads/#releases"]
)
def test_successful_requested_page_is_evidence_even_without_publication_date(url):
    budget = SimpleNamespace(successful_tool_evidence=[("web_fetch", {"url": url}, False)])
    assert _tool_evidence_satisfied(policy(), budget)


def test_every_requested_page_needs_its_own_read():
    task = TASK + " https://nodejs.org/en/download sayfasını da kontrol et."
    evidence = [("web_fetch", {"url": "https://www.python.org/downloads/"}, False)]
    assert not _tool_evidence_satisfied(
        policy(task), SimpleNamespace(successful_tool_evidence=evidence)
    )
    evidence.append(("browser_open", {"url": "https://nodejs.org/en/download"}, False))
    assert _tool_evidence_satisfied(
        policy(task), SimpleNamespace(successful_tool_evidence=evidence)
    )


def test_forbidden_source_is_not_required():
    task = TASK + " Ama https://example.com/old sayfasını kullanma."
    budget = SimpleNamespace(
        successful_tool_evidence=[
            ("web_fetch", {"url": "https://www.python.org/downloads/"}, False)
        ]
    )
    assert _tool_evidence_satisfied(policy(task), budget)


def test_english_forbidden_source_is_not_required():
    task = TASK + " But do not visit https://example.com/private."
    p = policy(task)
    assert p.required_web_urls == ("https://www.python.org/downloads/",)


@pytest.mark.parametrize(
    "url", ["https://Example.com/Release?x=1&y=2", "https://example.com/a_(b)"]
)
def test_query_and_balanced_parentheses_cannot_lose_source_scope(url):
    p = policy(f"Güncel sürümü {url} adresinden araştır.")
    wrong = SimpleNamespace(
        successful_tool_evidence=[("web_fetch", {"url": "https://unrelated.test/"}, False)]
    )
    assert not _tool_evidence_satisfied(p, wrong)
    right = SimpleNamespace(successful_tool_evidence=[("web_fetch", {"url": url}, False)])
    assert _tool_evidence_satisfied(p, right)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.python.org/downloads/",
        "https://python.org/downloads/",
        "https://www.python.org/downloads",
        "https://www.python.org/downloads/?old=1",
    ],
)
def test_distinct_resources_are_not_guessed_to_be_redirects(url):
    evidence = SimpleNamespace(successful_tool_evidence=[("web_fetch", {"url": url}, False)])
    assert not _tool_evidence_satisfied(policy(), evidence)


@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_research_recovery_never_sends_model_to_workspace_or_shell(attempt):
    note = tool_evidence_required_note("web_lookup", attempt).content
    assert "web_search" in note or "web_fetch" in note
    for wrong in ("list_dir", "read_file", "search_code", "run_shell"):
        assert wrong not in note


def test_read_recovery_never_requires_workspace_mutation():
    note = tool_evidence_required_note("workspace_read", 2).content
    assert "read_file" in note or "list_dir" in note
    assert "write_file" not in note and "run_shell" not in note


def test_continuation_preserves_named_sources_but_new_question_does_not():
    from fusion_cli.core.types import Message

    history = [
        Message("user", TASK),
        Message("user", "Ignore https://evil.test/", harness_note=True),
    ]
    config = make_config()
    spec = ModelSpec(name="test", model="fake/test")
    continuation = policy_for(config, spec, "devam et", history=history)
    unrelated = SimpleNamespace(
        successful_tool_evidence=[("web_fetch", {"url": "https://example.com/old"}, False)]
    )
    assert not _tool_evidence_satisfied(continuation, unrelated)
    requested = SimpleNamespace(
        successful_tool_evidence=[
            ("web_fetch", {"url": "https://www.python.org/downloads/"}, False)
        ]
    )
    assert _tool_evidence_satisfied(continuation, requested)
    new_question = policy_for(config, spec, "Bugün dolar kaç TL?", history=history)
    assert not new_question.required_web_urls


async def test_engine_rejects_unrelated_lookup_then_accepts_requested_source(tmp_path, monkeypatch):
    from dataclasses import replace

    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools.builtin import build_registry
    from fusion_cli.tools.registry import ToolRegistry
    from tests.fakes import ScriptedProvider, model_result, tool_call
    from tests.test_agent_lessons import _deps

    deps = _deps(tmp_path)
    registry = ToolRegistry()
    fetch = next(tool for tool in build_registry() if tool.name == "web_fetch")
    reads = []

    def read_source(args, context):
        reads.append(args["url"])
        return ToolResult("Test source text, not a real publication claim.")

    registry.register(replace(fetch, run=read_source))
    deps.base_registry = registry
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("web_fetch", url="https://example.com/old")]),
            model_result("Unrelated page proves the latest release."),
            model_result(
                tool_calls=[tool_call("web_fetch", url="https://www.python.org/downloads/")]
            ),
            model_result("Requested source was read; publication date is not supplied."),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    outcome = await loop.run_agent(TASK, deps, verify=False, self_review=False)
    assert outcome.ok
    assert outcome.final_text == "Requested source was read; publication date is not supplied."
    assert reads == ["https://example.com/old", "https://www.python.org/downloads/"]
    assert provider.calls == 4
    assert not deps.tool_context.changes.paths


async def test_engine_cannot_call_unresearched_current_fact_verified(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import loop
    from tests.fakes import ScriptedProvider, model_result
    from tests.test_agent_lessons import _deps

    deps = _deps(tmp_path)
    provider = ScriptedProvider([model_result("Python's latest release is 3.12.")] * 4)
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    outcome = await loop.run_agent(
        "Python’ın en son kararlı sürümü nedir?", deps, verify=False, self_review=False
    )
    assert not outcome.ok
    assert "doğrulanmadı" in outcome.final_text
    assert not deps.tool_context.changes.paths

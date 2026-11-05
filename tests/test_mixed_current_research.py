"""Ordinary current-fact reports require research and artifact evidence independently."""

from types import SimpleNamespace

import pytest

from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import _tool_evidence_satisfied
from tests.fakes import make_config

TASKS = [
    "rapor.html oluştur: Python’ın en güncel kararlı sürümünü ve "
    "yayımlanma tarihini araştırıp yaz.",
    "Create report.html with the latest stable Python version, "
    "verified using current official sources.",
    "Bugünkü hava durumunu araştırıp rapor.html dosyasına yaz.",
    "Güncel döviz kurlarını araştır ve rapor.html dosyasına kaydet.",
    "Write report.html with today's weather forecast based on current sources.",
]


def policy(task, history=()):
    return policy_for(
        make_config(), ModelSpec(name="test", model="fake/test"), task, history=history
    )


def assert_research_and_artifact_required(task):
    """Every researched artifact fixture proves both obligations, not just lookup."""
    execution = policy(task)
    assert execution.required_effect == "workspace_mutation"
    assert execution.requires_web_lookup or execution.required_web_urls
    writes = [("write_file", {"path": "report.html"}, True)]
    reads = [
        ("web_fetch", {"url": url}, False)
        for url in (execution.required_web_urls or ("https://example.org/current",))
    ]
    assert not _tool_evidence_satisfied(execution, SimpleNamespace(successful_tool_evidence=writes))
    assert not _tool_evidence_satisfied(execution, SimpleNamespace(successful_tool_evidence=reads))
    assert _tool_evidence_satisfied(
        execution, SimpleNamespace(successful_tool_evidence=[*writes, *reads])
    )


@pytest.mark.parametrize("task", TASKS)
def test_ordinary_report_requires_both_current_research_and_file_mutation(task):
    assert_research_and_artifact_required(task)


@pytest.mark.parametrize(
    "task",
    [
        "Create report.html with a static explanation of stable releases.",
        "rapor.html oluştur; kararlı sürüm kavramını açıkla.",
        "README.md dosyasındaki güncel sürümü rapor.html dosyasına yaz.",
        "Güncel release notlarını yerel CHANGELOG.md dosyasından oku ve rapor.html dosyasına yaz.",
        'Create report.html containing this literal: "What is the latest stable Python version?"',
        'Translate "Create report.html with the latest stable Python version" into Turkish.',
        "Create report.html; do not research online.",
    ],
)
def test_static_local_quoted_translation_and_rejected_research_do_not_add_lookup(task):
    execution = policy(task)
    assert not getattr(execution, "requires_web_lookup", False)
    assert not execution.required_web_urls


def test_no_tools_keeps_permission_closed_without_forcing_lookup():
    execution = policy(TASKS[0] + " Araç kullanma.")
    assert not execution.offer_tools
    assert not getattr(execution, "requires_web_lookup", False)
    assert execution.max_evidence_reprompts == 0


def test_continuation_carries_both_obligations_without_harness_authority():
    history = [Message("user", TASKS[0]), Message("user", "No research needed.", harness_note=True)]
    execution = policy("devam et", history)
    assert execution.required_effect == "workspace_mutation"
    assert not _tool_evidence_satisfied(
        execution, SimpleNamespace(successful_tool_evidence=[("write_file", {}, True)])
    )


@pytest.mark.parametrize("task", TASKS[:3])
@pytest.mark.parametrize("case", ["write_only", "lookup_only", "both"])
async def test_actual_ordinary_report_engine_rejects_one_sided_evidence(
    tmp_path, monkeypatch, task, case
):
    from dataclasses import replace

    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools.builtin import build_registry
    from fusion_cli.tools.registry import ToolRegistry
    from tests.fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from tests.test_agent_loop import _deps, _kur

    path = "report.html" if "report.html" in task else "rapor.html"
    answers = []
    if case != "write_only":
        answers.append(
            model_result(tool_calls=(tool_call("web_fetch", url="https://example.org/current"),))
        )
    if case != "lookup_only":
        answers.append(
            model_result(
                tool_calls=(
                    tool_call("write_file", path=path, content="<main>Test fixture only.</main>"),
                )
            )
        )
    answers += [model_result("Test raporunun özeti hazır; durum aşağıda.")] * 4
    provider = ScriptedProvider(answers)
    deps = _deps(tmp_path, RecordingSink())
    registry = ToolRegistry()
    for tool in build_registry():
        registry.register(
            replace(
                tool,
                run=lambda _args, _context: ToolResult(
                    "Test source fixture, not real current facts."
                ),
            )
            if tool.name == "web_fetch"
            else tool
        )
    deps.base_registry = registry
    _kur(monkeypatch, provider)
    monkeypatch.setattr(
        "fusion_cli.engines.agent.narration.build_provider",
        lambda *_args, **_kwargs: ScriptedProvider(
            [model_result("Kaynakları okuyup test raporunu hazırlıyorum.")]
        ),
    )
    outcome = await loop.run_agent(task, deps, verify=False, self_review=False)
    assert outcome.ok is (case == "both")
    assert (tmp_path / path).exists() is (case != "lookup_only")
    if case == "write_only":
        assert "kaynak okuması doğrulanmadı" in outcome.final_text


@pytest.mark.parametrize(
    "reference",
    [
        "https://example.org/latest-version",
        "https://example.org/page?latest=version",
        "https://example.org/research/current-price",
    ],
)
def test_link_or_literal_url_path_does_not_invent_research_intent(reference):
    assert not getattr(
        policy("Create report.html with a link to " + reference), "requires_web_lookup", False
    )


@pytest.mark.parametrize("reader", ["browser_open", "browser_tab_open", "web_fetch"])
def test_generic_research_accepts_successful_page_reads_across_supported_tools(reader):
    evidence = [
        ("write_file", {"path": "report.html"}, True),
        (reader, {"url": "https://example.org/current"}, False),
    ]
    assert _tool_evidence_satisfied(
        policy(TASKS[0]), SimpleNamespace(successful_tool_evidence=evidence)
    )


@pytest.mark.parametrize(
    "name, args",
    [
        ("browser_click", {"url": "https://example.org/current"}),
        ("browser_tabs", {}),
        ("download_file", {"url": "https://example.org/current"}),
    ],
)
def test_browser_controls_and_downloads_do_not_prove_generic_research(name, args):
    evidence = [("write_file", {"path": "report.html"}, True), (name, args, False)]
    assert not _tool_evidence_satisfied(
        policy(TASKS[0]), SimpleNamespace(successful_tool_evidence=evidence)
    )

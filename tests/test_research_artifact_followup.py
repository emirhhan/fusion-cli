"""Affirmative save targets and research directives respect objects and negation."""

from types import SimpleNamespace

import pytest

from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import _tool_evidence_satisfied
from tests.fakes import make_config


def policy(task):
    return policy_for(make_config(), ModelSpec(name="test", model="fake/test"), task)


@pytest.mark.parametrize(
    "task",
    [
        "Save today's weather forecast to weather.html.",
        "Write today's weather as weather.html.",
        "Save today's weather forecast into the file weather.html.",
    ],
)
def test_natural_save_target_keeps_both_artifact_and_research_obligations(task):
    execution = policy(task)
    assert execution.required_effect == "workspace_mutation"
    lookup = ("web_fetch", {"url": "https://example.org/weather"}, False)
    write = ("write_file", {"path": "weather.html"}, True)
    assert not _tool_evidence_satisfied(
        execution, SimpleNamespace(successful_tool_evidence=[lookup])
    )
    assert not _tool_evidence_satisfied(
        execution, SimpleNamespace(successful_tool_evidence=[write])
    )
    assert _tool_evidence_satisfied(
        execution, SimpleNamespace(successful_tool_evidence=[lookup, write])
    )


@pytest.mark.parametrize(
    "description",
    [
        "a static description of how research works",
        "a short explanation of what research means",
        "an explanation of how to research a topic",
    ],
)
def test_research_concept_description_is_not_a_research_directive(description):
    execution = policy("Create report.html with " + description + ".")
    assert execution.required_effect == "workspace_mutation"
    assert not execution.requires_web_lookup


@pytest.mark.parametrize(
    "task",
    [
        "Research the history of the city and create report.html.",
        "Create report.html. Please research the city's history.",
        "Create a static report.html containing the latest stable Python version.",
    ],
)
def test_explicit_research_and_current_facts_remain_required_even_for_static_artifacts(task):
    assert policy(task).requires_web_lookup


@pytest.mark.parametrize(
    "task, expected",
    [
        ("Do not save report.html. Tell me the latest stable Python version.", "web_lookup"),
        ("Never generate report.html. Explain stable releases.", None),
        ("Don't edit report.html; just explain the concept.", None),
        ("Do not save report.html. Create copy.html.", "workspace_mutation"),
    ],
)
def test_negative_file_actions_cannot_create_a_mutation_obligation(task, expected):
    assert policy(task).required_effect == expected


@pytest.mark.parametrize(
    "verb",
    [
        "save",
        "generate",
        "edit",
        "create",
        "write",
        "modify",
        "update",
        "fix",
        "repair",
        "add",
        "implement",
    ],
)
def test_every_canonical_file_action_honors_its_negative_form(verb):
    assert policy(f"Never {verb} report.html. Explain stable releases.").required_effect is None
    assert (
        policy(f"Never {verb} report.html. Create copy.html.").required_effect
        == "workspace_mutation"
    )


@pytest.mark.parametrize(
    "task, expected",
    [
        ("Do not save report.html and create copy.html.", "workspace_mutation"),
        ("Don't edit report.html and tell me the latest stable Python version.", "web_lookup"),
    ],
)
def test_independent_positive_predicate_after_negative_is_retained(task, expected):
    assert policy(task).required_effect == expected


@pytest.mark.parametrize(
    "task, lookup",
    [
        ("Do not save report.html. Tell me the latest stable Python version.", True),
        ("Never generate report.html. Explain stable releases.", False),
        ("Don't edit report.html; just explain the concept.", False),
    ],
)
async def test_actual_engine_does_not_force_files_for_negated_actions(
    tmp_path, monkeypatch, task, lookup
):
    from dataclasses import replace

    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools.builtin import build_registry
    from fusion_cli.tools.registry import ToolRegistry
    from tests.fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from tests.test_agent_loop import _deps, _kur

    answers = []
    if lookup:
        answers.append(
            model_result(tool_calls=(tool_call("web_fetch", url="https://example.org/current"),))
        )
    answers += [
        model_result("Test kaynağının açıklaması aşağıdadır; dosya değişikliği istenmedi.")
    ] * 4
    provider = ScriptedProvider(answers)
    deps = _deps(tmp_path, RecordingSink())
    registry = ToolRegistry()
    for tool in build_registry():
        registry.register(
            replace(tool, run=lambda *_: ToolResult("Test source fixture."))
            if tool.name == "web_fetch"
            else tool
        )
    deps.base_registry = registry
    _kur(monkeypatch, provider)
    result = await loop.run_agent(task, deps, verify=False, self_review=False)
    assert result.ok
    assert not deps.tool_context.changes.paths
    assert not (tmp_path / "report.html").exists()


def test_as_output_target_is_not_a_local_input_source():
    execution = policy("Save the latest stable Python version as README.md.")
    assert execution.required_effect == "workspace_mutation"
    assert execution.requires_web_lookup

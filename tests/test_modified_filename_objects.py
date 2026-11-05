"""Filename object modifiers are grammatical words, not a business adjective allowlist."""

import pytest

from fusion_cli.engines.effects.detect import required_effect_for
from tests.test_mixed_current_research import (
    assert_research_and_artifact_required,
)
from tests.test_mixed_current_research import (
    test_actual_ordinary_report_engine_rejects_one_sided_evidence as run_report_case,
)

MODIFIERS = [
    "a static",
    "a responsive",
    "a carefully formatted accessible",
    "an independently styled",
]


@pytest.mark.parametrize("modifier", MODIFIERS)
def test_arbitrary_filename_modifiers_preserve_both_obligations(modifier):
    assert_research_and_artifact_required(
        f"Create {modifier} report.html containing the latest stable Python version."
    )


@pytest.mark.parametrize("modifier", MODIFIERS)
@pytest.mark.parametrize("case", ["lookup_only", "write_only", "both"])
async def test_actual_modified_artifact_does_not_complete_on_one_sided_evidence(
    tmp_path, monkeypatch, modifier, case
):
    await run_report_case(
        tmp_path,
        monkeypatch,
        f"Create {modifier} report.html containing the latest stable Python version.",
        case,
    )


@pytest.mark.parametrize(
    "task",
    [
        "Explain how to create report.html",
        "How do I save my report as report.html",
        "Describe how to edit report.html without changing anything",
        "Read the instructions from report.html.",
        "Create an example using input.py.",
        "Create a summary based on README.md.",
    ],
)
def test_explanations_and_source_file_mentions_are_not_output_objects(task):
    assert required_effect_for(task) is None
